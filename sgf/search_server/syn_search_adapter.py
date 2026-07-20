#!/usr/bin/env python3
"""
syn_search_adapter.py — v0.7.0 with Synonym Expansion & POS‑Aware Resolution
=======================================================================

Wraps an existing glean‑search‑server with a three‑level matching pipeline
that combines vector similarity with ontological structure. Designed to
reject cross‑domain false positives that pure embedding search cannot catch.

**Architecture — Three Levels of Matching**

    Level 1 (L1) — Cosine Similarity + Lemma/POS Filter
        Standard vector search over the knowledge base. Returns top‑k
        candidates, then filters by lemma and part‑of‑speech if constraints
        are provided. Fast (sub‑ms). High recall, low precision.

    Level 2 (L2) — Ontology‑Slot Matching
        An LLM decomposes the query into ontological slots:
            HEAD           — the core entity (e.g., "driver", "wrench")
            MODIFIER       — qualifying words (e.g., "torque", "titanium")
            IS_A           — broader categories (e.g., "tool", "hand tool")
            HAS_PART       — parts (e.g., "handle", "blade")
            HAS_ATTRIBUTE  — attribute‑value pairs (e.g., material=titanium)
            HAS_PURPOSE    — what it is used for (e.g., "drive fasteners")
        Each slot lemma is resolved to a canonical ID, with synonym expansion
        and tool‑sense preference for HEAD.
        Each L1 candidate's definition is fetched, and a structural overlap
        score is computed with head matching weighted most heavily.

    Level 3 (L3) — Ancestor Propagation
        Same as L2, but also checks the candidate's hypernym ancestors
        (parents, grandparents, etc.) for IS_A matches, and the parts of
        parts for HAS_PART matches. Catches inherited structure that isn't
        directly listed on the candidate node.

**Key Improvements in v0.7.0**
    - Synonym lookup for HEAD: tries "screwdriver", "driver_tool", etc.
    - Tool‑keyword boosting: prefers senses with "tool", "screw", etc.
    - Multi‑result scoring: picks best across synonyms.
    - POS‑aware fallback: noun → adjective → unrestricted.
    - Canonical ID deduplication prevents repeats.

**Usage**

    # Default: all three levels, ancestor depth = 2
    python syn_search_adapter.py "titanium torque driver" --levels 3

    # Level 1 only (pure vector search)
    python syn_search_adapter.py "titanium torque driver" --levels 1

    # Level 1 + 2 only (no ancestor propagation)
    python syn_search_adapter.py "titanium torque driver" --levels 2

    # Custom ancestor depth (go 3 generations up)
    python syn_search_adapter.py "titanium torque driver" --levels 3 --ancestor-depth 3

**Exit Codes**

    0   — success, at least one result returned
    1   — success, zero results (no match found)
    2   — server connection error
    3   — LLM call failed
    4   — invalid arguments

**Requirements**

    - Python 3.10+
    - requests
    - llm_wrapper.py  (in same directory or on PATH)
    - query_ontology_prompt.txt  (in current directory, fallback to ontology_prompt.txt)
    - glean‑search‑server running on localhost:8400
"""

import sys
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from argparse import ArgumentParser, Namespace

# Fix for RawDescriptionHelpFormatter – works on Python 3.10+ and older
try:
    from argparse import RawDescriptionHelpFormatter
except ImportError:
    from argparse import RawTextHelpFormatter as RawDescriptionHelpFormatter

import requests

SERVER = "http://localhost:8400"
TEMP_DIR = Path("./temp")

# --- Synonym dictionary for common tool heads ---
TOOL_SYNONYMS = {
    "driver": ["screwdriver", "driver_tool", "screw_driver"],
    "wrench": ["spanner", "wrench_tool"],
    "drill": ["power_drill", "drill_tool"],
    "screwdriver": ["screw_driver", "driver"],
    "hammer": ["hammer_tool"],
    "pliers": ["pincer", "pliers_tool"],
    "saw": ["saw_tool"],
    "knife": ["blade", "knife_tool"],
    "blade": ["knife", "blade_tool"],
    "handle": ["grip", "handle_tool"],
    "tool": ["implement", "instrument", "device"],
}


class SynSearchAdapter:
    """
    A wrapper around the glean‑search‑server that adds ontology‑aware matching.

    The adapter implements three levels of matching (L1, L2, L3) as described
    in the module docstring. It does NOT modify the underlying server — all
    additional logic lives in this class.
    """

    def __init__(self, server_url: str = SERVER, llm_script: str = "llm_wrapper.py"):
        """
        Initialise the adapter.

        Args:
            server_url:  Base URL of the search server (e.g. "http://localhost:8400").
            llm_script:  Path to the `llm_wrapper.py` script.
        """
        self.server = server_url.rstrip('/')
        self.llm_script = llm_script

    # ------------------------------------------------------------------
    # Level 1 — Cosine Similarity + Lemma/POS Filter
    # ------------------------------------------------------------------

    def l1_search(self, text: str, k: int = 10,
                  lemma_restrict: str | None = None,
                  pos_restrict: str | None = None) -> list[dict]:
        """
        Perform Level‑1 search: cosine similarity with optional lemma/POS filters.

        Args:
            text:            Natural language query string.
            k:               Number of candidates to return.
            lemma_restrict:  If given, only return results whose lemma matches
                             this string (exact match).
            pos_restrict:    If given, only return results with this part‑of‑speech
                             (e.g. "noun", "verb").

        Returns:
            A list of candidate dicts. Empty list if server returns nothing or errors.

        Raises:
            requests.ConnectionError:  If the server is unreachable.
        """
        payload: dict[str, object] = {"text": text, "k": k}
        if lemma_restrict:
            payload["lemma_restrict"] = lemma_restrict
        if pos_restrict:
            payload["pos_restrict"] = pos_restrict

        try:
            resp = requests.post(f"{self.server}/search", json=payload, timeout=10)
            resp.raise_for_status()
            return resp.json().get("results", [])
        except requests.ConnectionError:
            print(f"ERROR: Cannot connect to search server at {self.server}", file=sys.stderr)
            raise
        except requests.RequestException as e:
            print(f"ERROR: Search request failed: {e}", file=sys.stderr)
            return []

    # ------------------------------------------------------------------
    # Level 2 — Ontology Extraction & Slot Resolution (CLI-based LLM)
    # ------------------------------------------------------------------

    def _generate_temp_filename(self, suffix: str = "prompt") -> tuple[Path, Path]:
        """Generate timestamp+uuid filenames for prompt and response."""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        random_id = uuid.uuid4().hex[:8]
        base = f"{timestamp}-{random_id}_{suffix}"
        prompt_path = TEMP_DIR / f"{base}_prompt.txt"
        resp_path = TEMP_DIR / f"{base}_response.txt"
        return prompt_path, resp_path

    def _call_llm_cli(self, prompt_text: str) -> str:
        """
        Call llm_wrapper.py via CLI, save prompt/response to ./temp.
        Returns the raw response text (everything outside XML tags, but we'll extract <answer>).
        """
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        prompt_path, resp_path = self._generate_temp_filename("ontology")

        prompt_path.write_text(prompt_text, encoding="utf-8")

        cmd = [
            sys.executable,
            self.llm_script,
            "--in-file", str(prompt_path),
            "--out-file", str(resp_path),
            "--verbose"
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                print(f"WARNING: llm_wrapper.py returned exit code {result.returncode}",
                      file=sys.stderr)
                print(f"stderr: {result.stderr[:500]}", file=sys.stderr)
                return ""
        except FileNotFoundError:
            print(f"ERROR: llm_wrapper.py not found at '{self.llm_script}'", file=sys.stderr)
            return ""
        except subprocess.TimeoutExpired:
            print(f"ERROR: llm_wrapper.py timed out after 120 seconds", file=sys.stderr)
            return ""
        except Exception as e:
            print(f"ERROR: Failed to run llm_wrapper.py: {e}", file=sys.stderr)
            return ""

        if not resp_path.exists():
            print(f"ERROR: Response file not created: {resp_path}", file=sys.stderr)
            return ""

        try:
            raw_response = resp_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"ERROR: Could not read response file: {e}", file=sys.stderr)
            return ""

        return raw_response

    def _extract_answer_tag(self, text: str) -> str:
        """
        Extract content inside <answer>...</answer> XML tags using procedural parsing.
        Returns the content (stripped) or empty string if not found.
        """
        start_tag = "<answer>"
        end_tag = "</answer>"
        start_idx = text.find(start_tag)
        if start_idx == -1:
            print("WARNING: No <answer> tag found in LLM response", file=sys.stderr)
            return ""
        end_idx = text.find(end_tag, start_idx)
        if end_idx == -1:
            print("WARNING: No closing </answer> tag found in LLM response", file=sys.stderr)
            return ""
        content_start = start_idx + len(start_tag)
        content = text[content_start:end_idx]
        return content.strip()

    def extract_ontology(self, text: str) -> dict:
        """
        Call LLM via CLI to decompose a query into ontological slots.
        Uses query_ontology_prompt.txt (compound‑decomposition format),
        falls back to ontology_prompt.txt if not present.

        Args:
            text:  Natural language query (e.g. "titanium torque driver").

        Returns:
            dict with keys HEAD, MODIFIER, IS_A, HAS_PART, HAS_ATTRIBUTE, HAS_PURPOSE.
            All values default to empty lists / empty string on failure.
        """
        prompt_path = Path("query_ontology_prompt.txt")
        if not prompt_path.exists():
            prompt_path = Path("ontology_prompt.txt")
        try:
            prompt_template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            print("ERROR: Neither query_ontology_prompt.txt nor ontology_prompt.txt found",
                  file=sys.stderr)
            return self._empty_ontology()

        full_prompt = prompt_template + "\n" + text

        raw_response = self._call_llm_cli(full_prompt)
        if not raw_response:
            return self._empty_ontology()

        answer = self._extract_answer_tag(raw_response)
        if not answer:
            answer = raw_response.strip()
            if not answer:
                return self._empty_ontology()

        return self._parse_ontology(answer)

    def _parse_ontology(self, text: str) -> dict:
        """
        Parse the LLM's answer into ontology slots including HEAD and MODIFIER.
        Expected format (each slot on its own line):
            HEAD: single noun
            MODIFIER: value1, value2
            IS_A: value1, value2
            HAS_PART: value1, value2
            HAS_ATTRIBUTE: attr1=val1, attr2=val2
            HAS_PURPOSE: single phrase
        """
        ontology = {
            "HEAD": "",
            "MODIFIER": [],
            "IS_A": [],
            "HAS_PART": [],
            "HAS_ATTRIBUTE": [],
            "HAS_PURPOSE": ""
        }

        current_slot = None

        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue

            found_slot = None
            value_part = ""

            upper_line = line.upper()
            for label in ["HEAD", "MODIFIER", "IS_A", "HAS_PART", "HAS_ATTRIBUTE", "HAS_PURPOSE"]:
                if upper_line.startswith(label + ":"):
                    found_slot = label
                    value_part = line[len(label) + 1:].strip()
                    break
                clean = line.lstrip(" *-•→")
                if clean.upper().startswith(label + ":"):
                    found_slot = label
                    value_part = clean[len(label) + 1:].strip()
                    break

            if found_slot:
                current_slot = found_slot
                if current_slot == "HEAD":
                    ontology[current_slot] = value_part
                elif current_slot == "HAS_PURPOSE":
                    ontology[current_slot] = value_part
                else:
                    values = [v.strip() for v in value_part.replace(";", ",").replace("|", ",").split(",") if v.strip()]
                    ontology[current_slot] = values
            elif current_slot:
                # Continuation line
                if current_slot == "HAS_PURPOSE":
                    if ontology[current_slot]:
                        ontology[current_slot] += " " + line
                    else:
                        ontology[current_slot] = line
                elif current_slot == "HEAD":
                    if not ontology[current_slot]:
                        ontology[current_slot] = line
                else:
                    values = [v.strip() for v in line.replace(";", ",").replace("|", ",").split(",") if v.strip()]
                    ontology[current_slot].extend(values)

        return ontology

    # ------------------------------------------------------------------
    # Enhanced Lemma Resolution with Synonyms
    # ------------------------------------------------------------------

    
    def resolve_lemma_with_synonyms(self, lemma: str, pos: str = "noun", prefer_tool: bool = True) -> dict:
        """
        Resolve lemma by trying exact lemma lookup first, then vector fallback.
        For ontology slots, exact lemma match is critical.

        Uses /lookup/lemma for exact matches (preferred) and /search (vector) as fallback.
        """
        lemmas_to_try = [lemma] + TOOL_SYNONYMS.get(lemma.lower(), [])
        best = None
        best_score = -1.0
        seen_cids: set[str] = set()

        # --- Step 1: Try exact lemma lookup via /lookup/lemma ---
        for l in lemmas_to_try:
            try:
                payload = {"lemma": l, "pos": pos, "policy": "research_unfiltered"}
                resp = requests.post(f"{self.server}/lookup/lemma", json=payload, timeout=10)
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    for r in results:
                        cid = r.get("canonical_id")
                        if not cid or cid in seen_cids:
                            continue
                        seen_cids.add(cid)
                        # Exact lemma match gets a high base score
                        score = 0.9   # high confidence for exact match
                        # Boost tool keywords
                        microgloss = (r.get("microgloss", "") + " " + r.get("lemma", "")).lower()
                        tool_kw = ["tool", "screw", "wrench", "driver", "drill", "hammer",
                                   "pliers", "saw", "blade", "knife", "spanner", "implement"]
                        bonus = 0.1 if any(kw in microgloss for kw in tool_kw) else 0.0
                        noun_bonus = 0.05 if ".noun." in cid else 0.0
                        adjusted = score + bonus + noun_bonus
                        if adjusted > best_score:
                            best_score = adjusted
                            best = r
            except requests.RequestException:
                continue

        if best:
            return {
                "canonical_id": best.get("canonical_id"),
                "lemma": best.get("lemma", lemma),
                "score": best.get("score", 0.9) if best.get("score") else 0.9,
                "microgloss": best.get("microgloss", ""),
                "original_lemma": lemma
            }

        # --- Step 2: Fallback to vector search (original logic) ---
        for l in lemmas_to_try:
            payload: dict[str, object] = {"text": l, "pos_restrict": pos, "k": 5}
            try:
                resp = requests.post(f"{self.server}/search", json=payload, timeout=10)
                if resp.status_code != 200:
                    continue
                results = resp.json().get("results", [])
                for r in results:
                    cid = r.get("canonical_id")
                    if not cid or cid in seen_cids:
                        continue
                    seen_cids.add(cid)
                    score = r.get("score", 0.0)
                    # Boost score if microgloss or lemma contains tool keywords
                    microgloss = (r.get("microgloss", "") + " " + r.get("lemma", "")).lower()
                    tool_kw = ["tool", "screw", "wrench", "driver", "drill", "hammer",
                               "pliers", "saw", "blade", "knife", "spanner", "implement"]
                    bonus = 0.2 if any(kw in microgloss for kw in tool_kw) else 0.0
                    noun_bonus = 0.15 if ".noun." in cid else 0.0
                    adjusted = score + bonus + noun_bonus
                    if adjusted > best_score:
                        best_score = adjusted
                        best = r
            except requests.RequestException:
                continue

        if best:
            return {
                "canonical_id": best.get("canonical_id"),
                "lemma": best.get("lemma", lemma),
                "score": best.get("score", 0.0),
                "microgloss": best.get("microgloss", ""),
                "original_lemma": lemma
            }

        # --- Step 3: Fallback to unrestricted search (any POS) ---
        try:
            resp = requests.post(f"{self.server}/search", json={"text": lemma, "k": 5}, timeout=10)
            if resp.status_code == 200:
                for r in resp.json().get("results", []):
                    if ".noun." in r.get("canonical_id", ""):
                        return {
                            "canonical_id": r.get("canonical_id"),
                            "lemma": r.get("lemma", lemma),
                            "score": r.get("score", 0.0),
                            "microgloss": r.get("microgloss", ""),
                            "original_lemma": lemma
                        }
        except requests.RequestException:
            pass

        return {
            "canonical_id": None,
            "lemma": lemma,
            "score": 0.0,
            "microgloss": f"Unresolved: {lemma}",
            "original_lemma": lemma
        }



    def annotate_ontology(self, ontology: dict) -> dict:
        """
        Replace every string lemma in the ontology with its resolved canonical info,
        using synonym expansion for HEAD.

        Args:
            ontology:  Raw output from `extract_ontology()`.

        Returns:
            Same structure, but each slot value is a list of dicts with resolved IDs.
        """
        annotated: dict = {}
        for slot, items in ontology.items():
            if slot == "HEAD":
                head_lemma = items.strip() if isinstance(items, str) else ""
                if head_lemma:
                    annotated[slot] = [self.resolve_lemma_with_synonyms(head_lemma, "noun")]
                else:
                    annotated[slot] = []
            elif slot == "HAS_PURPOSE":
                annotated[slot] = items
            elif slot == "MODIFIER":
                resolved: list[dict] = []
                for item in items:
                    if isinstance(item, str) and item.strip():
                        info = self.resolve_lemma_with_synonyms(item.strip(), "adj")
                        info["original_lemma"] = item.strip()
                        resolved.append(info)
                annotated[slot] = resolved
            else:
                # IS_A, HAS_PART, HAS_ATTRIBUTE – use existing logic, but with synonym-aware resolution
                resolved: list[dict] = []
                for item in items:
                    if isinstance(item, str):
                        if "=" in item:
                            parts = item.split("=", 1)
                            attr_name = parts[0].strip()
                            attr_value = parts[1].strip()
                            info = self.resolve_lemma_with_synonyms(attr_name, "adj")
                            info["original_attribute"] = attr_name
                            info["value"] = attr_value
                            resolved.append(info)
                        else:
                            info = self.resolve_lemma_with_synonyms(item, "noun")
                            info["original_lemma"] = item
                            resolved.append(info)
                    elif isinstance(item, dict):
                        resolved.append(item)
                    else:
                        resolved.append({"original_lemma": str(item), "canonical_id": None})
                annotated[slot] = resolved
        return annotated

    # ------------------------------------------------------------------
    # Level 2+3 — Structural Scoring
    # ------------------------------------------------------------------

    def fetch_definition(self, canonical_id: str) -> dict:
        """
        Retrieve the full knowledge‑base definition for a canonical ID.

        Calls `/lookup/canonical` on the search server.

        Args:
            canonical_id:  Full canonical path.

        Returns:
            dict describing the entity, or empty dict on failure.
        """
        try:
            resp = requests.post(f"{self.server}/definition", json={"canonical_id": canonical_id}, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException as e:
            print(f"WARNING: Failed to fetch definition for '{canonical_id}': {e}",
                  file=sys.stderr)
        return {}

    @staticmethod
    def _extract_lemmas(entries: list, key: str = "lemma") -> list[str]:
        """Helper: pull lemmas from a list of dicts or strings."""
        result: list[str] = []
        for entry in entries:
            if isinstance(entry, dict):
                lemma = entry.get(key, "")
                if lemma:
                    result.append(lemma.lower())
            elif isinstance(entry, str):
                if entry:
                    result.append(entry.lower())
        return result

    def fetch_ancestors(self, canonical_id: str, depth: int = 2) -> set[str]:
        """
        Fetch all ancestor lemmas by walking the hypernym chain.

        Args:
            canonical_id:  Starting node.
            depth:         How many generations to traverse.

        Returns:
            Set of lowercased ancestor lemmas.
        """
        ancestors: set[str] = set()
        seen: set[str] = {canonical_id}
        current: list[str] = [canonical_id]

        for generation in range(depth):
            next_level: list[str] = []
            for cid in current:
                defn = self.fetch_definition(cid)
                hypernyms = defn.get("hypernyms", [])
                for h in hypernyms:
                    lemma = h.get("lemma", "").lower() if isinstance(h, dict) else str(h).lower()
                    if lemma:
                        ancestors.add(lemma)
                    hid = h.get("canonical_id", "") if isinstance(h, dict) else ""
                    if hid and hid not in seen:
                        seen.add(hid)
                        next_level.append(hid)
            current = next_level
            if not current:
                break
        return ancestors

    def compute_slot_overlap(self, query_ontology: dict, candidate_id: str,
                             ancestor_depth: int = 0) -> dict:
        """
        Compare query ontology against candidate, including HEAD matching.
        Uses weighted scoring: HEAD 0.5, IS_A 0.3, parts 0.2, modifier bonus.

        Args:
            query_ontology:  Annotated ontology from `annotate_ontology()`.
            candidate_id:    The candidate to evaluate.
            ancestor_depth:  Number of hypernym generations to consider.

        Returns:
            dict with keys: head_match, isa_match, isa_total, part_match,
            part_total, modifier_match, struct_score.
        """
        defn = self.fetch_definition(candidate_id)
        cand_isa: list[str] = self._extract_lemmas(defn.get("hypernyms", []))
        cand_parts: list[str] = self._extract_lemmas(defn.get("parts", []))
        cand_lemma: str = defn.get("lemma", "").lower()

        if ancestor_depth > 0:
            ancestors = self.fetch_ancestors(candidate_id, depth=ancestor_depth)
            cand_isa = list(set(cand_isa) | ancestors)

        # HEAD matching (exact or partial)
        query_head_objs = query_ontology.get("HEAD", [])
        query_head: str = query_head_objs[0].get("original_lemma", "").lower() if query_head_objs else ""
        head_match = 0
        if query_head:
            if query_head in cand_lemma or cand_lemma in query_head:
                head_match = 1
            elif query_head in cand_isa:
                head_match = 1

        # Modifiers — count how many match (bonus only)
        query_mods = [m.get("original_lemma", "").lower()
                      for m in query_ontology.get("MODIFIER", []) if m]
        modifier_match = sum(1 for mod in query_mods if mod in cand_lemma or mod in cand_isa)

        # IS_A matching
        query_isa = [x.get("original_lemma", "").lower()
                     for x in query_ontology.get("IS_A", [])]
        query_isa = [q for q in query_isa if q]
        isa_match = sum(1 for q in query_isa if q in cand_isa)

        # HAS_PART matching
        query_parts = [x.get("original_lemma", "").lower()
                       for x in query_ontology.get("HAS_PART", [])]
        query_parts = [q for q in query_parts if q]
        part_match = sum(1 for q in query_parts if q in cand_parts)

        # Compute weighted structural score
        raw_score = 0.0
        weight_sum = 0.0

        if query_head:
            raw_score += head_match * 0.5
            weight_sum += 0.5

        if query_isa:
            raw_score += (isa_match / len(query_isa)) * 0.3
            weight_sum += 0.3

        if query_parts:
            raw_score += (part_match / len(query_parts)) * 0.2
            weight_sum += 0.2

        # Modifier bonus (capped at 0.1)
        modifier_bonus = min(modifier_match * 0.05, 0.1)

        struct_score = (raw_score / max(weight_sum, 0.01)) + modifier_bonus
        struct_score = min(struct_score, 1.0)

        return {
            "head_match": head_match,
            "isa_match": isa_match,
            "isa_total": len(query_isa),
            "part_match": part_match,
            "part_total": len(query_parts),
            "modifier_match": modifier_match,
            "struct_score": round(struct_score, 4)
        }

    # ------------------------------------------------------------------
    # Public Search API
    # ------------------------------------------------------------------

    def search(self, query: str, k: int = 5,
               levels: int = 3, ancestor_depth: int = 2,
               l1_k: int = 10,
               w_cosine: float = 0.4, w_struct: float = 0.6) -> dict:
        """
        Run the full multi‑level search pipeline.

        Args:
            query:           Natural language search string.
            k:               Number of final results to return.
            levels:          1 = L1 only, 2 = L1+L2, 3 = L1+L2+L3.
            ancestor_depth:  Only used when levels >= 3.
            l1_k:            Number of L1 candidates to retrieve.
            w_cosine:        Weight for cosine similarity.
            w_struct:        Weight for structural match.

        Returns:
            dict with query, levels_applied, ontology_extracted, ontology_resolved, results.

        Raises:
            ValueError:  If levels not 1, 2, or 3.
            requests.ConnectionError:  If search server unreachable.
        """
        if levels not in (1, 2, 3):
            raise ValueError(f"levels must be 1, 2, or 3; got {levels}")

        # L1: retrieve candidates
        raw_candidates: list[dict] = self.l1_search(query, k=l1_k)

        # L2: ontology extraction (skip for level 1)
        ontology: dict = {} if levels == 1 else self.extract_ontology(query)
        annotated: dict = {} if levels == 1 else self.annotate_ontology(ontology)

        # Score each candidate
        scored: list[dict] = []
        for cand in raw_candidates:
            cid: str | None = cand.get("canonical_id")
            if not cid:
                continue

            entry: dict = {
                "canonical_id": cid,
                "lemma": cand.get("lemma", ""),
                "cosine_score": cand.get("score", 0.0),
                "structural_score": 0.0,
                "combined_score": cand.get("score", 0.0),
                "overlap": {}
            }

            if levels >= 2:
                ad: int = ancestor_depth if levels >= 3 else 0
                overlap: dict = self.compute_slot_overlap(annotated, cid, ancestor_depth=ad)
                entry["structural_score"] = overlap["struct_score"]
                entry["overlap"] = overlap
                entry["combined_score"] = (
                    w_cosine * entry["cosine_score"] +
                    w_struct * entry["structural_score"]
                )

            scored.append(entry)

        # Sort by combined score descending
        scored.sort(key=lambda x: x["combined_score"], reverse=True)

        return {
            "query": query,
            "levels_applied": levels,
            "ancestor_depth": ancestor_depth if levels >= 3 else 0,
            "ontology_extracted": ontology,
            "ontology_resolved": annotated,
            "results": scored[:k],
            "total_candidates_evaluated": len(scored)
        }

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_ontology() -> dict:
        """Return a safely empty ontology structure."""
        return {
            "HEAD": "",
            "MODIFIER": [],
            "IS_A": [],
            "HAS_PART": [],
            "HAS_ATTRIBUTE": [],
            "HAS_PURPOSE": ""
        }


# ------------------------------------------------------------------
# CLI Entry Point
# ------------------------------------------------------------------

def parse_args() -> Namespace:
    """Parse command‑line arguments with detailed help."""
    parser = ArgumentParser(
        description="Ontology‑aware semantic search wrapper (v0.7.0 with synonym expansion)",
        epilog=(
            "Examples:\n"
            "  python syn_search_adapter.py \"titanium torque driver\"\n"
            "  python syn_search_adapter.py \"red screwdriver\" --levels 2\n"
            "  python syn_search_adapter.py \"tool with handle\" --levels 1\n"
            "  python syn_search_adapter.py \"steel wrench\" --levels 3 --ancestor-depth 3\n"
        ),
        formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "query",
        type=str,
        help="Natural language query string (required)"
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Number of top results to return after re‑ranking (default: 5)"
    )
    parser.add_argument(
        "--l1-k",
        type=int,
        default=10,
        help="Number of candidates to request from Level‑1 search "
             "(should be >= k; default: 10)"
    )
    parser.add_argument(
        "--levels",
        type=int,
        default=3,
        choices=[1, 2, 3],
        help=(
            "Which architectural levels to run:\n"
            "  1  →  Level 1 only (cosine + lemma/POS filter)\n"
            "  2  →  Level 1 + Level 2 (adds ontology‑slot matching)\n"
            "  3  →  Level 1 + Level 2 + Level 3 (adds ancestor propagation)\n"
            "Default: 3"
        )
    )
    parser.add_argument(
        "--ancestor-depth",
        type=int,
        default=2,
        help=(
            "Number of hypernym generations to walk for Level‑3 propagation.\n"
            "  0  →  direct hypernyms only (same as L2)\n"
            "  1  →  parents only\n"
            "  2  →  parents + grandparents  (default)\n"
            "  3  →  parents + grandparents + great‑grandparents\n"
            "Only used when --levels >= 3."
        )
    )
    parser.add_argument(
        "--server",
        type=str,
        default=SERVER,
        help=f"Base URL of glean‑search‑server (default: {SERVER})"
    )
    parser.add_argument(
        "--llm-script",
        type=str,
        default="llm_wrapper.py",
        help="Path to llm_wrapper.py script (default: llm_wrapper.py)"
    )
    parser.add_argument(
        "--weights",
        type=str,
        default="0.4,0.6",
        help=(
            "Comma‑separated cosine_weight,structural_weight for final score.\n"
            "Default: 0.4,0.6 (favour structural alignment)"
        )
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty‑print JSON output with indentation"
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = parse_args()

    # Parse weight string
    try:
        w_cos, w_str = [float(x) for x in args.weights.split(",")]
    except ValueError:
        print("ERROR: --weights must be two comma‑separated floats (e.g. 0.4,0.6)",
              file=sys.stderr)
        sys.exit(4)

    adapter = SynSearchAdapter(server_url=args.server, llm_script=args.llm_script)
    try:
        result = adapter.search(
            query=args.query,
            k=args.k,
            levels=args.levels,
            ancestor_depth=args.ancestor_depth if args.levels >= 3 else 0,
            l1_k=args.l1_k,
            w_cosine=w_cos,
            w_struct=w_str
        )
    except requests.ConnectionError as exc:
        print(f"ERROR: Cannot connect to search server at {args.server}: {exc}",
              file=sys.stderr)
        sys.exit(2)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(4)

    # Determine exit code
    exit_code = 0 if result["results"] else 1

    # Output
    output = json.dumps(result, indent=2 if args.pretty else None, default=str)
    print(output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()