#!/usr/bin/env python3
"""
mint_compound.py – Single-responsibility script for lexicalizing compound phrases.

This script detects whether a multi-word query phrase should be lexicalized
as a first-class concept in Synapedia, then mints the new entry via the
shared synapedia_mint module.

It uses three deterministic tests:
  1. Non-compositional meaning test
  2. Functional / relational role test
  3. Remove-clause test

Usage:
    python mint_compound.py --db synapedia.db --compound "torque driver" --head-noun driver
    python mint_compound.py --db synapedia.db --compound "computer virus detection" --head-noun detection

Exit status:
    0  – No compounds minted (decision NO or all already exist)
    >0 – Prints comma-separated entry IDs of minted compounds
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Import shared minting module
# ---------------------------------------------------------------------------
from synapedia_mint import mint_entry, entry_exists

logger = logging.getLogger("mint_compound")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEMP_DIR = Path("./temp")
TEMP_DIR.mkdir(exist_ok=True)
EMBED_SERVICE_URL = "http://localhost:18401"
DEFAULT_LLM_SOURCE = "cloud"

# Combined prompt with exhaustive enumeration instruction
COMBINED_PROMPT = """You are a lexicalization judge for the Synapedia knowledge base.

## TASK
Given a compound phrase (e.g., "computer virus detection", "platinum dental drill", "experimental drone aircraft"),
identify **all** sub‑phrases that deserve to become first‑class concepts.

## ENUMERATION STEP (mandatory)
First, list every contiguous 2‑word and 3‑word sub‑phrase of the input. For each candidate, apply the three tests (non‑compositional meaning, functional/relational role, remove‑clause). Only output those that pass at least one test.

## EXAMPLES

Phrase: "computer virus detection"
Head noun: detection
Candidates:
- "computer virus": non‑compositional (not biological), functional (virus implies infect, computer = location), remove‑clause (which virus?) → YES
- "virus detection": functional (detection implies find, virus = object), remove‑clause (detection of what?) → YES
- "computer virus detection": compositional (predictable from "computer virus" + "detection"), remove‑clause (still "virus detection") → NO
- "computer detection": doesn't make sense → NO (skipped)
Valid: computer virus, virus detection
Output:
DECISION: YES
Compound 1:
new_lemma: computer virus
new_gloss: The term "computer virus" is a noun that denotes a malicious software program designed to replicate itself and spread from one computer to another, often corrupting data or disrupting operations. It specifically characterizes self‑replicating code that attaches to legitimate programs, typically requiring user action to propagate. It is distinct from worms, Trojan horses, and ransomware, which use different infection vectors. Core conceptual equivalents include malware, virus, and computer worm. The conceptual domain frequently intersects with cybersecurity, antivirus software, and data protection.
new_microgloss: malicious_self_replicating_software
bow: malware, virus, worm, cybersecurity, antivirus, infection, software
is_a_parents: software, malware

Compound 2:
new_lemma: virus detection
new_gloss: The phrase "virus detection" is a noun that denotes the process of identifying the presence of malicious software, particularly viruses, in a computer system or network. It specifically characterizes techniques such as signature‑based scanning, heuristic analysis, and behavior monitoring used to locate and classify malware. It is distinct from virus prevention and virus removal, which are separate stages of security management. Core conceptual equivalents include malware detection, virus scanning, and threat detection. The conceptual domain frequently intersects with antivirus software, cybersecurity protocols, and endpoint protection.
new_microgloss: malware_identification_process
bow: malware detection, antivirus, scanning, heuristic, signature, cybersecurity
is_a_parents: detection, security_process

Phrase: "platinum dental drill"
Head noun: drill
Candidates:
- "dental drill": non‑compositional (specific drill), functional (drill implies rotate, dental = purpose), remove‑clause (which drill?) → YES
- "platinum drill": compositional, attribute → NO
- "platinum dental drill": compositional, attribute → NO
- "platinum dental": not a compound → NO
Valid: dental drill
Output:
DECISION: YES
Compound 1:
new_lemma: dental drill
new_gloss: The term "dental drill" is a noun that denotes a handheld rotary tool used by dentists to remove decayed tooth material and prepare cavities for fillings. It specifically characterizes high‑speed drills with a burr tip, typically powered by compressed air or an electric motor. It is distinct from surgical drills and laboratory drills due to its precise ergonomic design and water‑cooling features. Core conceptual equivalents include dentist's drill, handpiece, and dental handpiece. The conceptual domain frequently intersects with dentistry, tooth restoration, and oral surgery.
new_microgloss: dentist_rotary_tool
bow: dentist, drill, handpiece, cavity, filling, rotary, burr
is_a_parents: drill, hand_tool

Phrase: "experimental drone aircraft"
Head noun: aircraft
Candidates:
- "drone aircraft": non‑compositional (drone = specific unmanned aircraft), remove‑clause (which aircraft?) → YES
- "experimental drone": status attribute, remove‑clause (still drone) → NO
- "experimental aircraft": status attribute → NO
- "experimental drone aircraft": status attribute → NO
Valid: drone aircraft
Output:
DECISION: YES
Compound 1:
new_lemma: drone aircraft
new_gloss: The phrase "drone aircraft" is a noun that denotes an unmanned aerial vehicle (UAV) operated remotely or autonomously for various purposes including surveillance, reconnaissance, and delivery. It specifically characterizes fixed‑wing or multirotor aircraft without an onboard pilot, guided by onboard computers or ground control. It is distinct from manned aircraft and model aircraft used purely for recreation, as drone aircraft often carry payloads and sensors. Core conceptual equivalents include UAV, unmanned aerial vehicle, and remotely piloted aircraft. The conceptual domain frequently intersects with aviation, robotics, and military technology.
new_microgloss: unmanned_aerial_vehicle
bow: UAV, drone, unmanned, aerial, vehicle, aircraft, reconnaissance
is_a_parents: aircraft, vehicle

Phrase: "red house"
Head noun: house
Candidates:
- "red house": all tests fail → NO
Valid: none
Output:
DECISION: NO

## YOUR TURN
Phrase: "{phrase}"
Head noun: {head_noun}
Candidates:
[Your enumeration here]
Valid: [list of valid lemmas]
Output:
"""

# ---------------------------------------------------------------------------
# LLM interaction
# ---------------------------------------------------------------------------

def call_llm(prompt_text: str,
             source: str = DEFAULT_LLM_SOURCE,
             model: Optional[str] = None,
             max_retries: int = 3) -> str:
    """Call llm_wrapper.py with the prompt, return response text."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    rand = uuid.uuid4().hex[:6]
    prompt_path = TEMP_DIR / f"{ts}_{rand}_prompt.txt"
    response_path = TEMP_DIR / f"{ts}_{rand}_response.txt"
    prompt_path.write_text(prompt_text, encoding="utf-8")
    for attempt in range(1, max_retries + 1):
        cmd = [sys.executable, "llm_wrapper.py",
               "--in-file", str(prompt_path),
               "--out-file", str(response_path),
               "--source", source]
        if model:
            cmd.extend(["--model", model])
        try:
            subprocess.run(cmd, check=True, timeout=120)
            response = response_path.read_text(encoding="utf-8")
            return response
        except Exception as e:
            logger.warning(f"LLM attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                raise
    raise RuntimeError("LLM call failed after all retries.")


def parse_llm_response_multi(response: str) -> List[Dict[str, str]]:
    """
    Parse the combined LLM response for multiple compounds.
    Returns list of dicts, each with keys: new_lemma, new_gloss, new_microgloss,
    bow, is_a_parents.
    If decision is NO, returns empty list.
    """
    lines = response.strip().split('\n')
    decision = False
    compounds = []
    current_compound = {}
    for line in lines:
        line = line.strip()
        if line.startswith("DECISION:"):
            val = line[len("DECISION:"):].strip()
            decision = (val.upper() == "YES")
        elif re.match(r'^Compound\s+\d+:', line):
            if current_compound:
                compounds.append(current_compound)
                current_compound = {}
        elif ':' in line:
            colon_idx = line.index(':')
            key = line[:colon_idx].strip().lower()
            value = line[colon_idx + 1:].strip()
            if key in ('new_lemma', 'new_gloss', 'new_microgloss', 'bow', 'is_a_parents'):
                current_compound[key] = value
    # append last compound
    if current_compound and decision:
        compounds.append(current_compound)
    return compounds


# ---------------------------------------------------------------------------
# Detection + Generation (combined LLM call, multi‑output)
# ---------------------------------------------------------------------------

def detect_and_generate_multi(phrase: str, head_noun: str) -> List[Dict[str, str]]:
    """Call LLM to decide and output multiple compounds."""
    prompt = COMBINED_PROMPT.format(phrase=phrase, head_noun=head_noun)
    logger.info("LLM prompt for phrase '%s' sent.", phrase)
    response = call_llm(prompt)
    logger.debug("LLM response (first 2000 chars): %s", response[:2000])
    compounds = parse_llm_response_multi(response)
    return compounds


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Mint new compound lexicon entries (multi‑output).",
        epilog=(
            "Examples:\n"
            "  python mint_compound.py --db synapedia.db --compound \"torque driver\" --head-noun driver\n"
            "  python mint_compound.py --db synapedia.db --compound \"computer virus\" --head-noun virus --dry-run\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", required=True, help="Path to synapedia.db")
    parser.add_argument("--compound", required=True,
                        help="The compound phrase to evaluate (e.g., 'computer virus detection')")
    parser.add_argument("--head-noun", required=True,
                        help="Head noun of the compound (e.g., 'detection')")
    parser.add_argument("--pos", default="NOUN",
                        help="POS of the head noun (default: NOUN)")
    parser.add_argument("--embed-service", default=EMBED_SERVICE_URL)
    parser.add_argument("--llm-source", default=DEFAULT_LLM_SOURCE,
                        help="LLM source (e.g., cloud, local)")
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without writing")
    parser.add_argument("--verbose", action="store_true",
                        help="Verbose logging to stderr")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    logger.info("Evaluating compound '%s' with head noun '%s'",
                args.compound, args.head_noun)

    # Stage 1 & 3: Detection + Definition generation (multi‑compound)
    compounds = detect_and_generate_multi(args.compound, args.head_noun)

    if not compounds:
        logger.info("Decision: NO – no valid compounds found in '%s'.", args.compound)
        print(0)
        return 0

    logger.info("Decision: YES – found %d compound(s) to mint.", len(compounds))

    inserted_entry_ids = []

    for idx, comp in enumerate(compounds):
        lemma = comp.get("new_lemma", "").strip()
        if not lemma:
            logger.warning("Compound %d has no new_lemma, skipping.", idx + 1)
            continue

        # Duplicate detection (via shared module)
        if entry_exists(args.db, lemma):
            logger.info("Compound '%s' already exists in DB, skipping.", lemma)
            continue

        new_gloss = comp.get("new_gloss", "")
        new_microgloss = comp.get("new_microgloss", "")
        bow = comp.get("bow", "")

        if not new_gloss:
            logger.warning("Compound '%s' has no new_gloss, skipping.", lemma)
            continue

        # Parse parents from LLM response
        is_a_parents_str = comp.get("is_a_parents", "")
        if is_a_parents_str:
            parent_lemmas = [p.strip() for p in is_a_parents_str.split(",") if p.strip()]
            is_a_parents = [{"lemma": p, "gloss": ""} for p in parent_lemmas]
        else:
            is_a_parents = None

        if args.dry_run:
            logger.info(
                "DRY RUN: would mint compound '%s' with microgloss='%s', "
                "parents=%s",
                lemma, new_microgloss,
                [p["lemma"] for p in (is_a_parents or [])],
            )
            continue

        # Stage 2: Mint via shared module
        entry_id = mint_entry(
            db_path=args.db,
            lemma=lemma,
            gloss=new_gloss,
            pos_ud=args.pos,
            microgloss=new_microgloss,
            bow=bow,
            is_a_parents=is_a_parents,
            is_instance=False,
            embed_service_url=args.embed_service,
            trust_level="provisional",
        )

        if entry_id:
            inserted_entry_ids.append(entry_id)
            logger.info("Minted compound '%s' as entry_id=%d", lemma, entry_id)

    # Stage 4: Return entry_ids
    if inserted_entry_ids:
        print(",".join(str(eid) for eid in inserted_entry_ids))
    else:
        print(0)

    return 0


if __name__ == "__main__":
    sys.exit(main())