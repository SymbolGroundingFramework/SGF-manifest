#!/usr/bin/env python3
"""
compute_embeddings.py

Stage 5 of the SGF lexicon build pipeline.

For each sgf_lexicon row with a non-NULL embedding_text and no
sense_embedding row under the requested embedding_method, compute the
embedding vector via ONNX BGE and INSERT into sense_embedding.

Fingerprint computation is a SEPARATE stage (compute_sense_fingerprints.py).
This script writes only the embed vector + dim; content_fingerprint and
fingerprint_method stay NULL until Stage 6 fills them.

Models supported (via --embedding-method):
    bge-small-en-v1   -> Xenova/bge-small-en-v1.5  (33M params, 384-dim)
    bge-large-en-v1   -> Xenova/bge-large-en-v1.5  (335M params, 1024-dim)
    bge-m3-v1         -> Xenova/bge-m3             (568M params, 1024-dim, multilingual)

The --embedding-method string becomes the universe key in
sense_embedding.embedding_method. Fingerprints derived from one method
are NEVER comparable to fingerprints from another method.

Backends:
    --device cpu             CPUExecutionProvider
    --device dml             DmlExecutionProvider (AMD GPU on Windows)
    --device cuda            CUDAExecutionProvider (NVIDIA GPU)

If the requested device's provider isn't actually loaded, the script
HARD FAILS rather than silently falling back to CPU.

Priority (--by-frequency, default ON):
    Rows belonging to the most common lemmas (lowest frequency_rank in
    the lemma_frequency table) are processed first. Lemmas with no
    frequency entry sort to the end (the long tail).

    --top-n N        process at most N rows then stop
    --min-freq F     only rows whose lemma has rank <= F
    --no-frequency   disable priority ordering (process arbitrary)

Resumable:
    Every run skips rows that already have a sense_embedding row for the
    requested embedding_method. You can stop with Ctrl-C and restart
    freely.

Install:
    pip install onnxruntime-directml tokenizers huggingface_hub numpy
    (Do NOT also install plain onnxruntime — they conflict.)

USAGE:
    python compute_embeddings.py --target sgf_lexicon.db \\
        --embedding-method bge-small-en-v1 --device dml --batch-size 128

    python compute_embeddings.py --target sgf_lexicon.db \\
        --embedding-method bge-large-en-v1 --device dml --batch-size 64 \\
        --top-n 50000
"""

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Embedding method registry
# ---------------------------------------------------------------------------
# Maps user-facing method name to the ONNX model parameters.
# Adding a new embedder = adding a new entry here. No other code changes.

METHODS = {
    "bge-small-en-v1": {
        "model_repo": "Xenova/bge-small-en-v1.5",
        "model_file": "onnx/model.onnx",
        "model_data": None,                 # single-file model, no .onnx_data
        "tokenizer_repo": "BAAI/bge-small-en-v1.5",
        "expected_dim": 384,
        "default_max_length": 512,
        "embedding_text_column": "embedding_text_v1",   # first-pass / diagnostic
    },
    "bge-large-en-v1": {
        "model_repo": "Xenova/bge-large-en-v1.5",
        "model_file": "onnx/model.onnx",
        "model_data": None,           # single-file 1.34GB model, no .onnx_data
        "tokenizer_repo": "BAAI/bge-large-en-v1.5",
        "expected_dim": 1024,
        "default_max_length": 512,
        "embedding_text_column": "embedding_text_v2",   # production
    },
    "bge-m3-v1": {
        "model_repo": "Xenova/bge-m3",
        "model_file": "onnx/model.onnx",
        "model_data": "onnx/model.onnx_data",
        "tokenizer_repo": "BAAI/bge-m3",
        "expected_dim": 1024,
        "default_max_length": 512,
        "embedding_text_column": "embedding_text_v2",   # cross-language production
    },
}

DEFAULT_BATCH = 64
DEFAULT_MAX_LENGTH = 256
COMMIT_EVERY_BATCHES = 4  # commit every N batches


# ---------------------------------------------------------------------------
# Model + tokenizer loading
# ---------------------------------------------------------------------------

def _download_artifact(repo_id, filename):
    """Download a single file from Hugging Face Hub. Returns local path."""
    from huggingface_hub import hf_hub_download
    print(f"  downloading {repo_id}/{filename} ...")
    local_path = hf_hub_download(repo_id=repo_id, filename=filename)
    print(f"  cached: {local_path}")
    return local_path


def load_tokenizer(repo_id):
    from tokenizers import Tokenizer
    tok_path = _download_artifact(repo_id, "tokenizer.json")
    return Tokenizer.from_file(tok_path)


def load_onnx_session(model_repo, model_file, model_data, device):
    import onnxruntime as ort

    model_path = _download_artifact(model_repo, model_file)
    if model_data:
        _download_artifact(model_repo, model_data)

    providers_by_device = {
        "cpu":  ["CPUExecutionProvider"],
        "dml":  ["DmlExecutionProvider", "CPUExecutionProvider"],
        "cuda": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    }
    requested = providers_by_device.get(device.lower())
    if requested is None:
        raise ValueError(f"unknown device: {device!r}. use cpu, dml, or cuda.")

    available = ort.get_available_providers()
    chosen = [p for p in requested if p in available]
    if not chosen:
        raise RuntimeError(
            f"requested device '{device}' needs one of {requested}, "
            f"but onnxruntime only sees {available}. "
            f"install onnxruntime-directml or onnxruntime-gpu as needed."
        )

    # Hard-fail if the primary requested provider isn't available.
    if device.lower() != "cpu" and requested[0] not in available:
        raise RuntimeError(
            f"device={device!r} requires {requested[0]!r}, but it is not in "
            f"the available providers {available}. Refusing to silently fall "
            f"back to CPU. Install the right onnxruntime variant."
        )

    sess_opts = ort.SessionOptions()
    sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess_opts.intra_op_num_threads = max(1, (os.cpu_count() or 4) - 1)

    print(f"  creating ONNX session on providers: {chosen}")
    session = ort.InferenceSession(
        model_path, sess_options=sess_opts, providers=chosen
    )
    actual = session.get_providers()
    print(f"  active providers: {actual}")
    if device.lower() != "cpu" and actual[0] != requested[0]:
        raise RuntimeError(
            f"ONNX session loaded but did not activate {requested[0]!r}. "
            f"actual providers: {actual}. Refusing to run on the wrong "
            f"device — would silently use CPU."
        )
    print(f"  session input names: {[i.name for i in session.get_inputs()]}")
    return session


# ---------------------------------------------------------------------------
# Tokenize + encode
# ---------------------------------------------------------------------------

def _tokenize_batch(tokenizer, texts, max_length):
    import numpy as np
    tokenizer.enable_truncation(max_length=max_length)
    tokenizer.enable_padding(length=None)
    encodings = tokenizer.encode_batch(texts)
    input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
    attn_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
    return input_ids, attn_mask


def _cls_normalize(token_embeddings):
    """BGE recipe: take the [CLS] token (index 0), L2-normalize."""
    import numpy as np
    dense = token_embeddings[:, 0, :]
    norms = np.linalg.norm(dense, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (dense / norms).astype(np.float32)


def embed_batch(session, tokenizer, texts, max_length):
    import numpy as np
    input_ids, attn_mask = _tokenize_batch(tokenizer, texts, max_length)

    inputs = {"input_ids": input_ids, "attention_mask": attn_mask}
    expected_names = {i.name for i in session.get_inputs()}
    if "token_type_ids" in expected_names:
        inputs["token_type_ids"] = np.zeros_like(input_ids)

    outputs = session.run(None, inputs)
    token_embeddings = outputs[0]
    if token_embeddings.ndim == 3:
        return _cls_normalize(token_embeddings)
    norms = np.linalg.norm(token_embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (token_embeddings / norms).astype(np.float32)


# ---------------------------------------------------------------------------
# Pending-row selection
# ---------------------------------------------------------------------------

def _resolve_embedding_text_column(read_conn, embedding_method):
    """Pick which embedding_text column to read for this method.

    Looks up METHODS[embedding_method]['embedding_text_column']. Falls
    back to 'embedding_text' (single-pass legacy column) when the v1/v2
    column is empty across the board -- this keeps the script compatible
    with older builds where only the single column was populated.
    """
    method_cfg = METHODS.get(embedding_method, {})
    preferred = method_cfg.get("embedding_text_column", "embedding_text")

    cur = read_conn.cursor()
    cols = {r[1] for r in cur.execute("PRAGMA table_info(sgf_lexicon)")}
    if preferred not in cols:
        return "embedding_text"

    cur.execute(
        f"SELECT COUNT(*) FROM sgf_lexicon WHERE {preferred} IS NOT NULL"
    )
    n_preferred = cur.fetchone()[0]
    if n_preferred > 0:
        return preferred

    if "embedding_text" in cols:
        cur.execute(
            "SELECT COUNT(*) FROM sgf_lexicon WHERE embedding_text IS NOT NULL"
        )
        n_legacy = cur.fetchone()[0]
        if n_legacy > 0:
            print(f"  note: {preferred} is empty; falling back to embedding_text")
            return "embedding_text"

    return preferred


def materialize_pending(read_conn, embedding_method, by_frequency,
                        top_n, min_freq, limit_lemma, only_wsids=None):
    """Pull pending rows into memory, ordered by priority.

    "Pending" means: has the right embedding_text column populated,
    no row in sense_embedding for this embedding_method.

    If only_wsids is a non-empty iterable, the existence-check on
    sense_embedding is REMOVED so we always (re)compute those rows.
    This is used by repair_audit_failures.py to force recomputation
    after an improver pass changed the embedding_text.

    Returns list of (wsid, embedding_text) tuples.
    """
    print("Materializing pending rows ...")
    t0 = time.time()

    et_col = _resolve_embedding_text_column(read_conn, embedding_method)

    wsid_list = list(only_wsids) if only_wsids else None
    if wsid_list:
        placeholders = ",".join("?" * len(wsid_list))
        base = f"""
            SELECT sl.wiktionary_source_id, sl.{et_col}, sl.lemma
            FROM sgf_lexicon sl
            WHERE sl.{et_col} IS NOT NULL
              AND sl.wiktionary_source_id IN ({placeholders})
        """
        params = list(wsid_list)
    else:
        base = f"""
            SELECT sl.wiktionary_source_id, sl.{et_col}, sl.lemma
            FROM sgf_lexicon sl
            WHERE sl.{et_col} IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM sense_embedding se
                  WHERE se.wiktionary_source_id = sl.wiktionary_source_id
                    AND se.embedding_method = ?
              )
        """
        params = [embedding_method]

    if limit_lemma and not wsid_list:
        base += " AND LOWER(sl.lemma) = LOWER(?)"
        params.append(limit_lemma)

    if by_frequency:
        sql = f"""
            SELECT sub.wiktionary_source_id, sub.{et_col}
            FROM ({base}) sub
            LEFT JOIN lemma_frequency lf ON lf.lemma = LOWER(sub.lemma)
            {"WHERE lf.frequency_rank IS NOT NULL AND lf.frequency_rank <= ?"
             if min_freq is not None else ""}
            ORDER BY
                CASE WHEN lf.frequency_rank IS NULL THEN 1 ELSE 0 END,
                lf.frequency_rank ASC,
                sub.wiktionary_source_id
        """
        if min_freq is not None:
            params.append(min_freq)
    else:
        sql = f"SELECT wiktionary_source_id, {et_col} FROM ({base}) ORDER BY wiktionary_source_id"

    if top_n is not None:
        sql += f" LIMIT {int(top_n)}"

    cur = read_conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    elapsed = time.time() - t0
    print(f"  {len(rows):,} rows pending ({elapsed:.1f}s)")
    return rows


def count_total_for_method(read_conn, embedding_method):
    et_col = _resolve_embedding_text_column(read_conn, embedding_method)
    cur = read_conn.cursor()
    cur.execute(f"""
        SELECT COUNT(*) FROM sgf_lexicon
        WHERE {et_col} IS NOT NULL
    """)
    total = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM sense_embedding
        WHERE embedding_method = ?
    """, (embedding_method,))
    done = cur.fetchone()[0]
    return total, done


# ---------------------------------------------------------------------------
# Main embedding loop
# ---------------------------------------------------------------------------

def run(db_path, embedding_method, device, batch_size, max_length,
        by_frequency, top_n, min_freq, limit_lemma, only_wsids=None):

    meta = METHODS.get(embedding_method)
    if meta is None:
        print(f"Unknown --embedding-method: {embedding_method!r}", file=sys.stderr)
        print(f"Known methods: {sorted(METHODS.keys())}", file=sys.stderr)
        return 1

    print(f"Loading tokenizer from {meta['tokenizer_repo']} ...")
    tokenizer = load_tokenizer(meta["tokenizer_repo"])
    print(f"Loading ONNX model {meta['model_repo']}/{meta['model_file']} on device={device} ...")
    session = load_onnx_session(
        meta["model_repo"], meta["model_file"], meta["model_data"], device
    )
    print(f"  model loaded.")
    print()

    read_conn = sqlite3.connect(db_path)
    read_conn.execute("PRAGMA query_only = ON")
    write_conn = sqlite3.connect(db_path)
    write_conn.execute("PRAGMA journal_mode = WAL")
    write_conn.execute("PRAGMA synchronous = NORMAL")

    total, done = count_total_for_method(read_conn, embedding_method)
    print(f"Method: {embedding_method}")
    print(f"  sgf_lexicon rows with embedding_text : {total:,}")
    print(f"  already done for this method          : {done:,}")
    print(f"  remaining                             : {total - done:,}")
    print()

    rows = materialize_pending(
        read_conn, embedding_method, by_frequency, top_n, min_freq, limit_lemma,
        only_wsids=only_wsids,
    )
    if not rows:
        print("Nothing to embed.")
        read_conn.close()
        write_conn.close()
        return 0
    print()

    write_cur = write_conn.cursor()
    processed = 0
    t_start = time.time()
    last_report = t_start
    batches_since_commit = 0

    n_rows = len(rows)
    for batch_start in range(0, n_rows, batch_size):
        batch = rows[batch_start:batch_start + batch_size]
        ids = [r[0] for r in batch]
        texts = [r[1] for r in batch]

        vectors = embed_batch(session, tokenizer, texts, max_length)
        dim = int(vectors.shape[1])

        if dim != meta["expected_dim"]:
            raise RuntimeError(
                f"Embedder returned dim={dim}, expected {meta['expected_dim']} "
                f"for method {embedding_method!r}. Aborting."
            )

        now_ts = int(time.time())
        params = [
            (sense_id, embedding_method, dim, vec.tobytes(), now_ts)
            for sense_id, vec in zip(ids, vectors)
        ]
        write_cur.executemany("""
            INSERT OR REPLACE INTO sense_embedding (
                wiktionary_source_id, embedding_method, embedding_dim,
                embed, computed_at
            ) VALUES (?, ?, ?, ?, ?)
        """, params)

        # advance maturity_tier based on which embedder ran.
        # bge-small -> 'embedded_v1' (only from 'raw'/'provisional').
        # bge-large -> 'embedded_v2' (only from 'raw'..'improved').
        # Other embedders (bge-m3, custom) advance to embedded_v2 by
        # default since they are production-quality.
        if "small" in embedding_method.lower():
            advance_sql = (
                "UPDATE sgf_lexicon SET maturity_tier = 'embedded_v1' "
                "WHERE wiktionary_source_id = ? "
                "AND maturity_tier IN ('raw','provisional')"
            )
        else:
            advance_sql = (
                "UPDATE sgf_lexicon SET maturity_tier = 'embedded_v2' "
                "WHERE wiktionary_source_id = ? "
                "AND maturity_tier IN ('raw','provisional','embedded_v1','improved')"
            )
        write_cur.executemany(advance_sql, [(sid,) for sid, _ in zip(ids, vectors)])

        processed += len(batch)
        batches_since_commit += 1

        if batches_since_commit >= COMMIT_EVERY_BATCHES:
            write_conn.commit()
            batches_since_commit = 0

        now = time.time()
        if now - last_report >= 5.0:
            elapsed = now - t_start
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = n_rows - processed
            eta_min = (remaining / rate / 60) if rate > 0 else 0
            print(f"  embedded {processed:,} / {n_rows:,} "
                  f"({100.0 * processed / n_rows:.1f}%)  "
                  f"{rate:.1f} rows/s  ETA {eta_min:.1f} min")
            last_report = now

    write_conn.commit()
    read_conn.close()
    write_conn.close()
    return processed


def main():
    p = argparse.ArgumentParser(
        description="Compute BGE embeddings via ONNX into sense_embedding."
    )
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--embedding-method", required=True,
                   choices=sorted(METHODS.keys()),
                   help="Which embedder to run")
    p.add_argument("--device", default="cpu", choices=["cpu", "dml", "cuda"])
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    p.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH,
                   help="Tokenizer truncation length (BGE supports up to 512 for en, 8192 for m3)")
    p.add_argument("--by-frequency", dest="by_frequency", action="store_true",
                   default=True,
                   help="Process most-frequent lemmas first (default ON)")
    p.add_argument("--no-frequency", dest="by_frequency", action="store_false",
                   help="Process arbitrary order, ignore frequency table")
    p.add_argument("--top-n", type=int, default=None,
                   help="Process at most N rows then stop")
    p.add_argument("--min-freq", type=int, default=None,
                   help="Only rows whose lemma has frequency_rank <= F")
    p.add_argument("--lemma", default=None,
                   help="Limit to a single lemma (case-insensitive)")
    p.add_argument("--wsids", default=None,
                   help="Comma-separated wsids to recompute (forces "
                        "recomputation regardless of existing rows)")
    args = p.parse_args()

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"Target DB not found: {db_path}", file=sys.stderr)
        return 1

    print(f"Target:          {db_path.resolve()}")
    print(f"Method:          {args.embedding_method}")
    print(f"Device:          {args.device}")
    print(f"Batch:           {args.batch_size}    MaxLen: {args.max_length}")
    print(f"By-frequency:    {args.by_frequency}")
    if args.top_n is not None:
        print(f"Top-N limit:     {args.top_n:,}")
    if args.min_freq is not None:
        print(f"Min rank cutoff: {args.min_freq:,}")
    if args.lemma:
        print(f"Lemma:           {args.lemma}")
    print()

    try:
        processed = run(
            db_path=db_path,
            embedding_method=args.embedding_method,
            device=args.device,
            batch_size=args.batch_size,
            max_length=args.max_length,
            by_frequency=args.by_frequency,
            top_n=args.top_n,
            min_freq=args.min_freq,
            limit_lemma=args.lemma,
            only_wsids=(
                [int(x) for x in args.wsids.split(",") if x.strip()]
                if args.wsids else None
            ),
        )
    except ImportError as e:
        print(f"\nMissing dependency: {e}", file=sys.stderr)
        print("Install with:", file=sys.stderr)
        print("  pip install onnxruntime tokenizers huggingface_hub numpy", file=sys.stderr)
        print("For AMD GPU (Windows DirectML), use:", file=sys.stderr)
        print("  pip uninstall onnxruntime", file=sys.stderr)
        print("  pip install onnxruntime-directml", file=sys.stderr)
        return 1

    # Summary
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM sense_embedding WHERE embedding_method = ?
    """, (args.embedding_method,))
    n_total = cur.fetchone()[0]
    conn.close()

    print()
    print("=" * 60)
    print("EMBEDDING COMPUTE COMPLETE")
    print("=" * 60)
    print(f"  processed this run        : {processed:,}")
    print(f"  total for method {args.embedding_method!r:>20}: {n_total:,}")
    print(f"  output db                 : {db_path.resolve()}")
    print()
    print("Next step:")
    print(f"  python compute_sense_fingerprints.py --target {db_path.name} "
          f"--embedding-method {args.embedding_method}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
