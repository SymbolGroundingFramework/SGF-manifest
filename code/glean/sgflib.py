"""
sgflib.py

The shared library for every GLEAN script. Provides:

  - load_config()          : find and parse sgf.toml
  - LexiconClient          : opens the lexicon DB, runs the four-step
                             lookup cascade against it
  - get_embedder()         : module-level singleton; loads the ONNX model
                             ONCE per process
  - LLMClient              : thin wrapper around a local-LLM HTTP endpoint;
                             talks MDKV, not JSON
  - parse_mdkv() / format_mdkv()
  - The 15 closed semantic roles, exposed as ROLES

Every other GLEAN script should `from sgflib import ...` rather than
duplicate lookup, embedding, or LLM logic.

Design notes:
  - The embedder is cached at module level (option A from the planning
    discussion). Within a single Python process the model loads once.
    A future persistent embedder service is possible via a different
    LexiconClient subclass without changing callers.
  - The lookup cascade is the deterministic-first ladder: exact ->
    cosine -> LLM rerank -> micro-mint. Each level logs the decision.
  - All LLM I/O is MDKV. JSON is for inter-script Python data only.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib                # Python 3.11+
except ImportError:               # pragma: no cover
    import tomli as tomllib       # type: ignore


# =============================================================================
# The closed grammar — fifteen semantic roles
# =============================================================================

CORE_ROLES = (
    "HAS_AGENT",
    "HAS_PATIENT",
    "HAS_THEME",
    "HAS_EXPERIENCER",
    "HAS_RECIPIENT",
    "HAS_BENEFICIARY",
)

CONTEXTUAL_ROLES = (
    "HAS_TIME",
    "HAS_LOCATION",
    "HAS_SOURCE",
    "HAS_DESTINATION",
    "HAS_MANNER",
    "HAS_INSTRUMENT",
    "HAS_CAUSE",
    "HAS_REASON",
    "HAS_ATTRIBUTE",
)

ROLES = CORE_ROLES + CONTEXTUAL_ROLES
assert len(ROLES) == 15, "the closed grammar must have exactly 15 roles"


# =============================================================================
# Literal entity types
# =============================================================================
# Entities of these types are 'literals' — they get a canonical_id of the
# form lit.<subtype>.<normalized_value> and are NOT looked up in the lexicon.
# Lexicon cosine search would just produce noise for them.
#
# We grant node-status to year-granularity dates and small integers, on the
# principle that they're navigable hops ("what else happened in 1792?").
# We DENY node-status to specific calendar dates, large numbers, decimals,
# money, and percentages — those stay as target_surface on the spoke, not
# as nodes. See entity_census._classify_literal() for the cut.

LITERAL_TYPES = frozenset({
    "year",         # 4-digit year, e.g. lit.year.1792
    "int_small",    # integer 0-1000, e.g. lit.int.9
})

# spaCy NER labels that COULD be literals (we still decide per-instance)
LITERAL_NER_LABELS = frozenset({
    "DATE", "TIME", "CARDINAL", "ORDINAL",
    "MONEY", "PERCENT", "QUANTITY",
})


# =============================================================================
# Reporting verbs (loaded lazily from reporting_verbs.txt)
# =============================================================================

_REPORTING_VERBS_CACHE: set[str] | None = None


def get_reporting_verbs(bundle_dir: Path | None = None) -> set[str]:
    """Load and cache the reporting-verb lemma list.

    These are the verbs that, when present as a clause's governing verb,
    trigger attribution-based POV assignment. The subject of the
    reporting verb is the POV speaker, NOT the document author.
    """
    global _REPORTING_VERBS_CACHE
    if _REPORTING_VERBS_CACHE is not None:
        return _REPORTING_VERBS_CACHE
    p = (bundle_dir or Path(__file__).resolve().parent) / "reporting_verbs.txt"
    verbs: set[str] = set()
    if p.exists():
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            verbs.add(line.lower())
    _REPORTING_VERBS_CACHE = verbs
    return verbs


# =============================================================================
# Config loader
# =============================================================================

@dataclass
class Config:
    """Parsed sgf.toml. Plain data — callers read fields directly."""
    raw: dict
    config_path: Path

    @property
    def lexicon_db_path(self) -> Path:
        return Path(self.raw["lexicon"]["db_path"])

    @property
    def default_embedding_method(self) -> str:
        return self.raw["lexicon"]["default_embedding_method"]

    @property
    def synapse_store_path(self) -> Path:
        return Path(self.raw["synapse_store"]["db_path"])


def _find_config_path() -> Path:
    env = os.environ.get("SGF_CONFIG")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p
        raise FileNotFoundError(
            f"SGF_CONFIG points to {p} but no file found there."
        )

    cwd_cfg = Path.cwd() / "sgf.toml"
    if cwd_cfg.exists():
        return cwd_cfg

    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", "")) / "sgf" / "sgf.toml"
        if appdata.exists():
            return appdata
    else:
        home_cfg = Path.home() / ".config" / "sgf" / "sgf.toml"
        if home_cfg.exists():
            return home_cfg

    # Last resort: look next to the script itself
    script_cfg = Path(__file__).resolve().parent / "sgf.toml"
    if script_cfg.exists():
        return script_cfg

    raise FileNotFoundError(
        "Could not find sgf.toml. Set SGF_CONFIG env var, or put sgf.toml "
        "in the current directory, or in the GLEAN install directory."
    )


def load_config(path: Path | str | None = None) -> Config:
    """Find and parse sgf.toml. Returns a Config object."""
    cfg_path = Path(path) if path else _find_config_path()
    with open(cfg_path, "rb") as f:
        raw = tomllib.load(f)
    return Config(raw=raw, config_path=cfg_path)


# =============================================================================
# Embedder singleton — load the ONNX model ONCE per process
# =============================================================================

_EMBEDDER_CACHE: dict[tuple[str, str], "OnnxEmbedder"] = {}


class OnnxEmbedder:
    """ONNX-based query embedder. Mirrors the recipe used by the lexicon
    pipeline's compute_embeddings.py so query vectors live in the same
    space as the lexicon's stored vectors.

    Lazy-loads the model on first use. Subsequent calls reuse the loaded
    session and tokenizer.
    """

    def __init__(self, method: str, device: str, max_length: int,
                 model_repo: str, model_file: str, model_data: str | None,
                 tokenizer_repo: str):
        self.method = method
        self.device = device
        self.max_length = max_length
        self.model_repo = model_repo
        self.model_file = model_file
        self.model_data = model_data
        self.tokenizer_repo = tokenizer_repo
        self._session = None
        self._tokenizer = None
        self._dim = None

    def _load(self):
        if self._session is not None:
            return
        from huggingface_hub import hf_hub_download
        import onnxruntime as ort
        from tokenizers import Tokenizer

        # Download tokenizer
        tok_path = hf_hub_download(repo_id=self.tokenizer_repo,
                                   filename="tokenizer.json")
        self._tokenizer = Tokenizer.from_file(tok_path)

        # Download model files
        model_path = hf_hub_download(repo_id=self.model_repo,
                                     filename=self.model_file)
        if self.model_data:
            hf_hub_download(repo_id=self.model_repo, filename=self.model_data)

        # Pick providers
        providers_map = {
            "cpu":  ["CPUExecutionProvider"],
            "dml":  ["DmlExecutionProvider", "CPUExecutionProvider"],
            "cuda": ["CUDAExecutionProvider", "CPUExecutionProvider"],
        }
        requested = providers_map.get(self.device.lower(), ["CPUExecutionProvider"])
        available = ort.get_available_providers()
        chosen = [p for p in requested if p in available]
        if not chosen:
            raise RuntimeError(
                f"No matching ONNX provider for device={self.device!r}. "
                f"Requested {requested}, only {available} available."
            )

        sess_opts = ort.SessionOptions()
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(model_path,
                                             sess_options=sess_opts,
                                             providers=chosen)

    def embed(self, texts: list[str]) -> "list":
        """Embed a list of strings. Returns L2-normalized float32 vectors."""
        import numpy as np
        self._load()

        self._tokenizer.enable_truncation(max_length=self.max_length)
        self._tokenizer.enable_padding(length=None)
        encs = self._tokenizer.encode_batch(texts)

        input_ids = np.array([e.ids for e in encs], dtype=np.int64)
        attn = np.array([e.attention_mask for e in encs], dtype=np.int64)

        feed = {"input_ids": input_ids, "attention_mask": attn}
        expected = {i.name for i in self._session.get_inputs()}
        if "token_type_ids" in expected:
            feed["token_type_ids"] = np.zeros_like(input_ids)

        outputs = self._session.run(None, feed)
        token_embeddings = outputs[0]

        if token_embeddings.ndim == 3:
            # Take [CLS] (first token), L2-normalize. Same recipe as the
            # lexicon pipeline.
            dense = token_embeddings[:, 0, :]
        else:
            dense = token_embeddings

        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        out = (dense / norms).astype(np.float32)
        self._dim = int(out.shape[1])
        return out


def get_embedder(cfg: Config, method: str | None = None) -> OnnxEmbedder:
    """Module-level singleton accessor. First call loads the model;
    subsequent calls return the cached embedder."""
    method = method or cfg.default_embedding_method
    device = cfg.raw["embedder"]["device"]
    max_length = cfg.raw["embedder"]["max_length"]
    key = (method, device)

    if key in _EMBEDDER_CACHE:
        return _EMBEDDER_CACHE[key]

    model_repo = cfg.raw["embedder"]["model_repos"].get(method)
    tokenizer_repo = cfg.raw["embedder"]["tokenizer_repos"].get(method)
    if not model_repo or not tokenizer_repo:
        raise ValueError(f"No embedder registered for method={method!r} in sgf.toml")

    # Determine whether the model has a separate .onnx_data file. Hardcoded
    # to avoid network probes during config load. Add new methods here.
    has_onnx_data = {
        "bge-small-en-v1": False,
        "bge-large-en-v1": False,
        "bge-m3-v1":       True,
    }
    model_data = "onnx/model.onnx_data" if has_onnx_data.get(method, False) else None

    emb = OnnxEmbedder(
        method=method,
        device=device,
        max_length=max_length,
        model_repo=model_repo,
        model_file="onnx/model.onnx",
        model_data=model_data,
        tokenizer_repo=tokenizer_repo,
    )
    _EMBEDDER_CACHE[key] = emb
    return emb


# =============================================================================
# MDKV — Markdown-delimited key-value
# =============================================================================
# Used for all LLM input/output. JSON is for Python-to-Python data only.
#
# Format:
#   :::block_kind
#   key: value
#   key: value
#   multiline_key: |
#     line one
#     line two
#   :::
#
# Multi-block files are separated by blank lines. Fence kind is optional
# but recommended.

MDKV_FENCE_RE = re.compile(r"^:::\s*(\S+)?\s*$")


def format_mdkv(kind: str, fields: dict[str, Any]) -> str:
    """Render a dict as an MDKV block."""
    lines = [f":::{kind}"]
    for key, val in fields.items():
        if val is None:
            continue
        if isinstance(val, (list, tuple)):
            val = ", ".join(str(v) for v in val)
        sval = str(val)
        if "\n" in sval:
            lines.append(f"{key}: |")
            for inner in sval.splitlines():
                lines.append(f"  {inner}")
        else:
            lines.append(f"{key}: {sval}")
    lines.append(":::")
    return "\n".join(lines)


def parse_mdkv(text: str) -> list[dict[str, Any]]:
    """Parse MDKV text. Returns a list of {kind, ...fields} dicts.

    Tolerant of LLM variance: whitespace, trailing colons, partial fences.
    """
    blocks = []
    current: dict | None = None
    multiline_key: str | None = None
    multiline_buf: list[str] = []

    for raw in text.splitlines():
        line = raw.rstrip()

        # Multiline accumulator: indented line continues a `key: |` block
        if multiline_key is not None and (raw.startswith("  ") or raw.startswith("\t")):
            multiline_buf.append(raw.lstrip())
            continue
        if multiline_key is not None:
            current[multiline_key] = "\n".join(multiline_buf)
            multiline_key = None
            multiline_buf = []

        # Fence line
        fence = MDKV_FENCE_RE.match(line)
        if fence:
            if current is not None:
                blocks.append(current)
                current = None
            kind = fence.group(1) or ""
            if kind:
                current = {"_kind": kind}
            continue

        if current is None:
            # Lines outside any fenced block are ignored.
            continue

        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val == "|":
            multiline_key = key
            multiline_buf = []
        else:
            current[key] = val

    if current is not None:
        if multiline_key is not None:
            current[multiline_key] = "\n".join(multiline_buf)
        blocks.append(current)
    return blocks


# =============================================================================
# LLM client — local-LLM HTTP, MDKV in & out
# =============================================================================

class LLMClient:
    """Talks to an OpenAI-compatible chat completions endpoint. Designed
    for Llama-cpp, Ollama, or any equivalent local server. Also works
    with DeepSeek and OpenAI when the endpoint and api_key are set.

    Always uses MDKV for the structured output. The system prompt
    instructs the model to wrap its response in :::<kind> ... ::: fences.
    """

    def __init__(self, cfg: Config):
        self.endpoint = cfg.raw["llm"]["endpoint"]
        self.model = cfg.raw["llm"]["model"]
        self.api_key = cfg.raw["llm"].get("api_key", "")
        self.timeout = cfg.raw["llm"].get("timeout_seconds", 60)
        self.temperature = cfg.raw["llm"].get("temperature", 0.1)
        self.max_tokens = cfg.raw["llm"].get("max_tokens", 1024)

    def complete(self, system: str, user: str) -> str:
        """Send a chat completion request and return the raw response text."""
        import urllib.request
        import urllib.error

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(self.endpoint, data=data, headers=headers,
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.URLError as e:
            raise RuntimeError(f"LLM request failed: {e}") from e

        obj = json.loads(body)
        try:
            return obj["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(
                f"Unexpected LLM response shape: {obj}"
            ) from e

    def complete_mdkv(self, system: str, user: str,
                      expected_kind: str | None = None) -> list[dict]:
        """Run a completion and parse the response as MDKV. Returns the
        list of MDKV blocks."""
        raw = self.complete(system, user)
        blocks = parse_mdkv(raw)
        if expected_kind:
            blocks = [b for b in blocks if b.get("_kind") == expected_kind]
        return blocks


# =============================================================================
# Lookup result
# =============================================================================

@dataclass
class LookupCandidate:
    canonical_id: str
    lemma: str
    pos_simple: str
    microgloss: str
    gloss: str
    cosine: float


@dataclass
class LookupResult:
    target: str
    context: str
    pos_hint: str | None
    decision_level: int           # 1=exact, 2=cosine, 3=llm, 4=mint
    decision_reason: str
    canonical_id: str | None
    confidence: float
    candidates: list[LookupCandidate] = field(default_factory=list)
    minted: bool = False          # true if level 4 created a new entry

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "context": self.context,
            "pos_hint": self.pos_hint,
            "decision_level": self.decision_level,
            "decision_reason": self.decision_reason,
            "canonical_id": self.canonical_id,
            "confidence": self.confidence,
            "minted": self.minted,
            "candidates": [
                {
                    "canonical_id": c.canonical_id,
                    "lemma": c.lemma,
                    "pos": c.pos_simple,
                    "microgloss": c.microgloss,
                    "gloss": c.gloss,
                    "cosine": round(c.cosine, 4),
                }
                for c in self.candidates
            ],
        }


# =============================================================================
# LexiconClient — the workhorse
# =============================================================================

class LexiconClient:
    """Opens the lexicon SQLite DB and runs the four-step lookup cascade.

    Usage:
        cfg = load_config()
        lex = LexiconClient(cfg)
        result = lex.lookup(target="bank", context="I deposited money at the bank.")
        print(result.canonical_id, result.confidence, result.decision_level)
    """

    def __init__(self, cfg: Config, embedding_method: str | None = None):
        self.cfg = cfg
        self.method = embedding_method or cfg.default_embedding_method
        self.db_path = cfg.lexicon_db_path
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Lexicon DB not found at {self.db_path}. "
                f"Check [lexicon].db_path in {cfg.config_path}."
            )
        # Two connections: read-only and a lazy writer for micro-mint
        self._read = sqlite3.connect(self.db_path)
        self._read.execute("PRAGMA query_only = ON")
        self._write = None                          # lazy

        self._top_k = cfg.raw["lookup"]["top_k"]
        self._auto_accept_cosine = cfg.raw["lookup"]["auto_accept_cosine"]
        self._auto_accept_margin = cfg.raw["lookup"]["auto_accept_margin"]
        self._escalate_below = cfg.raw["lookup"]["escalate_below_cosine"]

        # Schema mapping
        s = cfg.raw["lexicon"]["schema"]
        self._parent_table = s["parent_table"]
        self._parent_id = s["parent_id_col"]
        self._parent_lemma = s["parent_lemma_col"]
        self._parent_pos = s["parent_pos_col"]
        self._parent_mg = s["parent_microgloss_col"]
        self._parent_gloss = s["parent_gloss_col"]
        self._parent_cid = s["parent_canonical_id_col"]
        self._embed_table = s["embed_table"]
        self._embed_id = s["embed_id_col"]
        self._embed_method = s["embed_method_col"]
        self._embed_dim = s["embed_dim_col"]
        self._embed_vector = s["embed_vector_col"]

        # Lazy resources
        self._embedder: OnnxEmbedder | None = None
        self._llm: LLMClient | None = None

        # In-memory cache of (canonical_id, vector) for ANN search.
        # Loaded on first lookup. For 1.76M rows x 1024 dims x 4B = ~7GB
        # for bge-large; we materialize only the IDs and a numpy matrix.
        self._cid_index: list | None = None
        self._vec_index = None                      # numpy array
        self._lemma_idx: dict | None = None         # lemma -> list of row indices

    # -------------------------------------------------------------
    # Cascade entry point
    # -------------------------------------------------------------

    def lookup(self, target: str, context: str = "",
               pos_hint: str | None = None,
               surrounding: str = "",
               *,
               enable_llm: bool = True,
               enable_mint: bool = True) -> LookupResult:
        """Run the four-step cascade for one target term."""

        result = LookupResult(
            target=target, context=context, pos_hint=pos_hint,
            decision_level=0, decision_reason="", canonical_id=None,
            confidence=0.0,
        )

        # ---- Step 1: exact lemma match ----
        exact = self._step1_exact(target, pos_hint)
        if exact is not None:
            result.decision_level = 1
            result.decision_reason = "exact lemma match"
            result.canonical_id = exact.canonical_id
            result.confidence = 1.0
            result.candidates = [exact]
            return result

        # ---- Step 2: cosine search ----
        candidates = self._step2_cosine(target, context, pos_hint, surrounding)
        result.candidates = candidates
        if candidates:
            top = candidates[0]
            margin = top.cosine - candidates[1].cosine if len(candidates) > 1 else top.cosine
            if (top.cosine >= self._auto_accept_cosine and
                    margin >= self._auto_accept_margin):
                result.decision_level = 2
                result.decision_reason = (
                    f"cosine accept (cos={top.cosine:.3f}, margin={margin:.3f})"
                )
                result.canonical_id = top.canonical_id
                result.confidence = float(top.cosine)
                return result

            # ---- Step 3: LLM rerank ----
            if enable_llm and top.cosine >= self._escalate_below:
                pick = self._step3_llm_rerank(target, context, surrounding,
                                              candidates)
                if pick is not None:
                    result.decision_level = 3
                    result.decision_reason = "LLM rerank"
                    result.canonical_id = pick.canonical_id
                    result.confidence = float(pick.cosine)
                    return result

        # ---- Step 4: mint micro-lexicon entry ----
        if enable_mint:
            minted_cid = self._step4_mint(target, pos_hint, context)
            result.decision_level = 4
            result.decision_reason = "micro-lexicon mint"
            result.canonical_id = minted_cid
            result.confidence = 0.5
            result.minted = True
            return result

        # Nothing worked and minting disabled
        result.decision_level = 0
        result.decision_reason = "no resolution"
        return result

    # -------------------------------------------------------------
    # Step 1: exact lemma match
    # -------------------------------------------------------------

    def _step1_exact(self, target: str,
                     pos_hint: str | None) -> LookupCandidate | None:
        sql = (
            f"SELECT {self._parent_cid}, {self._parent_lemma}, "
            f"       {self._parent_pos}, {self._parent_mg}, {self._parent_gloss} "
            f"FROM {self._parent_table} "
            f"WHERE LOWER({self._parent_lemma}) = LOWER(?) "
        )
        params: list = [target]
        if pos_hint:
            sql += f"AND {self._parent_pos} = ? "
            params.append(pos_hint)
        sql += "LIMIT 2"

        cur = self._read.execute(sql, params)
        rows = cur.fetchall()
        if len(rows) != 1:
            # 0 = no match; 2+ = ambiguous (multiple senses), skip step 1
            return None
        cid, lemma, pos, mg, gloss = rows[0]
        return LookupCandidate(canonical_id=cid, lemma=lemma, pos_simple=pos,
                               microgloss=mg, gloss=gloss, cosine=1.0)

    # -------------------------------------------------------------
    # Step 2: cosine search
    # -------------------------------------------------------------

    def _ensure_index_loaded(self):
        """Load the entire embedding matrix and id list into RAM. Done once.

        For 1.76M rows at 1024 dims this is ~7GB; at 384 dims ~2.6GB.
        Acceptable on the user's 128GB workstation.
        """
        if self._vec_index is not None:
            return

        import numpy as np
        print(f"[sgflib] loading lexicon embedding matrix (method={self.method}) ...",
              file=sys.stderr)
        t0 = time.time()
        cur = self._read.execute(f"""
            SELECT sl.{self._parent_cid}, sl.{self._parent_lemma},
                   sl.{self._parent_pos}, sl.{self._parent_mg}, sl.{self._parent_gloss},
                   se.{self._embed_dim}, se.{self._embed_vector}
            FROM {self._embed_table} se
            JOIN {self._parent_table} sl
              ON sl.{self._parent_id} = se.{self._embed_id}
            WHERE se.{self._embed_method} = ?
        """, (self.method,))

        rows = cur.fetchall()
        if not rows:
            raise RuntimeError(
                f"No sense_embedding rows found for method={self.method!r}. "
                f"Either the lexicon hasn't been embedded yet, or the "
                f"default_embedding_method in sgf.toml is wrong."
            )

        dim = rows[0][5]
        n = len(rows)
        cids = []
        lemmas = []
        poses = []
        mgs = []
        glosses = []
        matrix = np.empty((n, dim), dtype=np.float32)
        for i, (cid, lemma, pos, mg, gloss, _dim, blob) in enumerate(rows):
            cids.append(cid)
            lemmas.append(lemma)
            poses.append(pos)
            mgs.append(mg)
            glosses.append(gloss)
            matrix[i] = np.frombuffer(blob, dtype=np.float32)

        self._cid_index = list(zip(cids, lemmas, poses, mgs, glosses))
        self._vec_index = matrix

        # Lemma -> row indices, for POS-filtered narrowing
        lemma_idx: dict[str, list[int]] = {}
        for i, lemma in enumerate(lemmas):
            lemma_idx.setdefault(lemma.lower(), []).append(i)
        self._lemma_idx = lemma_idx

        elapsed = time.time() - t0
        print(f"[sgflib] loaded {n:,} vectors of dim {dim} ({elapsed:.1f}s)",
              file=sys.stderr)

    def _step2_cosine(self, target: str, context: str,
                      pos_hint: str | None,
                      surrounding: str) -> list[LookupCandidate]:
        import numpy as np

        self._ensure_index_loaded()
        if self._embedder is None:
            self._embedder = get_embedder(self.cfg, method=self.method)

        # Build the structured query text. Mirror the lexicon's embedding_text
        # field shape so query and index are in the same shape:
        #     iso_lang:en|lemma:X|pos:X|context:X|surrounding:X
        # No microgloss, no gloss (we don't know them yet).
        parts = [
            "iso_lang:en",
            f"lemma:{target}",
        ]
        if pos_hint:
            parts.append(f"pos:{pos_hint}")
        if context:
            parts.append(f"context:{context.strip()[:240]}")
        if surrounding:
            parts.append(f"surrounding:{surrounding.strip()[:240]}")
        query_text = "|".join(parts)

        qvec = self._embedder.embed([query_text])[0]  # already L2-normalized

        # ---- Lemma-restricted candidate pool ---------------------------
        # The whole point of a lexicon lookup is to find senses for THIS
        # lemma. Doing cosine across all 1.76M senses lets unrelated
        # senses win on context similarity alone (e.g. "aeroplaned" beating
        # "bank.riverside" for the query "sat on the bank"). Restrict the
        # search to rows whose lemma matches target (or a morphological
        # stem of target), and fall back to global only if nothing matches.
        target_lower = target.lower()
        candidate_rows = list(self._lemma_idx.get(target_lower, []))

        # Try simple morphological stems if exact lemma missed. The lexicon
        # often stores inflected forms as separate entries pointing to a
        # base lemma, but base lemmas are also present -- so for "banked"
        # or "banking" we ALSO check "bank".
        if not candidate_rows or len(candidate_rows) < 5:
            for suffix in ("ing", "ed", "s", "es", "er", "est", "ly"):
                if target_lower.endswith(suffix) and len(target_lower) > len(suffix) + 2:
                    stem = target_lower[:-len(suffix)]
                    candidate_rows.extend(self._lemma_idx.get(stem, []))
                    # Double consonant collapse ("banking" -> "bank" needed
                    # no collapse, but "running" -> "run" needs one)
                    if len(stem) >= 2 and stem[-1] == stem[-2]:
                        candidate_rows.extend(
                            self._lemma_idx.get(stem[:-1], [])
                        )
            # de-dup while preserving order
            seen_rows = set()
            unique = []
            for r in candidate_rows:
                if r not in seen_rows:
                    seen_rows.add(r)
                    unique.append(r)
            candidate_rows = unique

        if candidate_rows:
            # Restricted search: compute cosine ONLY over the candidate
            # rows for this lemma. Fast (typically <100 rows).
            idx_arr = np.array(candidate_rows, dtype=np.int64)
            sub_matrix = self._vec_index[idx_arr]
            sub_sims = sub_matrix @ qvec.astype(np.float32)

            if pos_hint:
                sub_poses = np.array(
                    [self._cid_index[r][2] for r in candidate_rows]
                )
                penalty = (sub_poses != pos_hint).astype(np.float32) * 0.05
                sub_sims = sub_sims - penalty

            k_sub = min(self._top_k, sub_sims.shape[0])
            sub_top = np.argpartition(-sub_sims, k_sub - 1)[:k_sub]
            sub_top = sub_top[np.argsort(-sub_sims[sub_top])]

            out: list[LookupCandidate] = []
            for j in sub_top:
                row = candidate_rows[int(j)]
                cid, lemma, pos, mg, gloss = self._cid_index[row]
                out.append(LookupCandidate(
                    canonical_id=cid, lemma=lemma, pos_simple=pos,
                    microgloss=mg, gloss=gloss, cosine=float(sub_sims[j])
                ))
            return out

        # ---- Fallback: lemma not in lexicon at all ---------------------
        # Original global cosine search. Used for proper nouns and
        # truly novel words that will likely fall through to mint anyway.
        sims = self._vec_index @ qvec.astype(np.float32)
        if pos_hint:
            poses = np.array([c[2] for c in self._cid_index])
            penalty = (poses != pos_hint).astype(np.float32) * 0.05
            sims = sims - penalty
        k = min(self._top_k, sims.shape[0])
        top_idx = np.argpartition(-sims, k - 1)[:k]
        top_idx = top_idx[np.argsort(-sims[top_idx])]
        out: list[LookupCandidate] = []
        for i in top_idx:
            cid, lemma, pos, mg, gloss = self._cid_index[i]
            out.append(LookupCandidate(
                canonical_id=cid, lemma=lemma, pos_simple=pos,
                microgloss=mg, gloss=gloss, cosine=float(sims[i])
            ))
        return out

    # -------------------------------------------------------------
    # Step 3: LLM rerank
    # -------------------------------------------------------------

    def _step3_llm_rerank(self, target: str, context: str,
                          surrounding: str,
                          candidates: list[LookupCandidate]) -> LookupCandidate | None:
        if self._llm is None:
            self._llm = LLMClient(self.cfg)

        cand_lines = []
        for i, c in enumerate(candidates):
            cand_lines.append(
                f"  {i + 1}. {c.canonical_id}  pos={c.pos_simple}\n"
                f"     microgloss: {c.microgloss}\n"
                f"     gloss: {c.gloss}"
            )
        cand_block = "\n".join(cand_lines)

        user = (
            f"Target word: {target}\n"
            f"Context sentence: {context}\n"
            f"Surrounding text: {surrounding}\n\n"
            f"Candidate senses from the lexicon:\n{cand_block}\n\n"
            f"Pick the ONE candidate whose sense matches the target's usage "
            f"in the context. If none match well, output candidate_index: 0.\n\n"
            f"Respond in MDKV:\n"
            f":::sense_pick\n"
            f"candidate_index: <integer 1-{len(candidates)} or 0 if none match>\n"
            f"rationale: <one short sentence>\n"
            f":::"
        )
        system = (
            "You are a lexicographer. Pick the single best sense for a word "
            "given its context. Respond only with the MDKV block."
        )

        try:
            blocks = self._llm.complete_mdkv(system, user, expected_kind="sense_pick")
        except Exception as e:
            print(f"[sgflib] LLM call failed in step 3: {e}", file=sys.stderr)
            return None

        if not blocks:
            return None

        block = blocks[0]
        try:
            idx = int(block.get("candidate_index", "0"))
        except ValueError:
            idx = 0
        if idx <= 0 or idx > len(candidates):
            return None
        return candidates[idx - 1]

    # -------------------------------------------------------------
    # Step 4: mint a micro-lexicon entry
    # -------------------------------------------------------------

    def _step4_mint(self, target: str,
                    pos_hint: str | None,
                    context: str) -> str:
        """Mint a document-scoped canonical_id for the target.

        For v1: we return a deterministic canonical_id string. We do NOT
        write to a database here; that's the responsibility of the
        compile_document.py orchestrator, which maintains the
        document-scoped micro-lexicon.
        """
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", target.lower()).strip("_") or "unknown"
        pos = (pos_hint or "noun").lower()
        return f"doc.{slug}.unmapped.{pos}.docloc"

    # -------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------

    def close(self):
        self._read.close()
        if self._write is not None:
            self._write.close()


# =============================================================================
# Convenience
# =============================================================================

def quick_lookup(target: str, context: str = "", pos_hint: str | None = None,
                 surrounding: str = "") -> dict:
    """One-shot lookup that loads config, lexicon, and embedder on demand.
    Useful for the `sgf lookup` CLI and ad-hoc testing.

    Returns a dict suitable for json.dump.
    """
    cfg = load_config()
    lex = LexiconClient(cfg)
    try:
        res = lex.lookup(target=target, context=context,
                         pos_hint=pos_hint, surrounding=surrounding)
    finally:
        lex.close()
    return res.as_dict()
