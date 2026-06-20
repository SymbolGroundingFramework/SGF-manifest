#!/usr/bin/env python3
"""
compute_sense_fingerprints.py

Optional Stage 12 of the SGF lexicon build pipeline.

This script computes a stable SimHash over a SENSE'S embedding so
that cache invalidation downstream can detect when a sense's content
has changed without comparing full vectors.

This is NOT the same thing as a content fingerprint over running
prose (which lives in the GLEAN bundle and operates on claims /
paragraphs, not on senses).

For each sense_embedding row under the requested embedding_method that
has a NULL content_fingerprint, compute a simhash fingerprint from the
stored embedding vector and write it back into the same row.

ALGORITHM
---------
The fingerprint is the sign bits of the L2-normalized embedding,
packed bytewise and base64url-encoded (no padding).

  N dims of float32 -> N sign bits -> N/8 bytes -> base64url string

For a 384-dim embedding: 384 bits, 48 bytes, 64 base64url chars.
For a 1024-dim embedding: 1024 bits, 128 bytes, 171 base64url chars.

The fingerprint string is recorded together with a fingerprint_method
label of the form 'simhash{N}-{embedding-method}', e.g.:

    simhash384-bge-small-en-v1
    simhash1024-bge-large-en-v1
    simhash1024-bge-m3-v1

Fingerprints from different fingerprint_methods are NEVER comparable.
Hamming-distance is only meaningful between two fingerprints sharing
the same fingerprint_method string.

PRIORITY (--by-frequency, default ON)
-------------------------------------
Same as compute_embeddings.py: rows belonging to the most common lemmas
are processed first.

  --top-n N        process at most N sense_embedding rows then stop
  --min-freq F     only rows whose lemma has frequency_rank <= F
  --no-frequency   disable priority ordering

RESUMABLE
---------
Every run skips sense_embedding rows that already have a non-NULL
content_fingerprint under the requested embedding_method.

USAGE
-----
    python compute_sense_fingerprints.py --target sgf_lexicon.db \\
        --embedding-method bge-small-en-v1

    python compute_sense_fingerprints.py --target sgf_lexicon.db \\
        --embedding-method bge-large-en-v1 --top-n 100000

    # Self-test (synthetic inputs, no DB):
    python compute_sense_fingerprints.py --self-test

    # Compare two specific senses:
    python compute_sense_fingerprints.py --target sgf_lexicon.db --compare \\
        --embedding-method bge-large-en-v1 \\
        en.bank.financial_institution.noun.core \\
        en.bank.river_edge.noun.core
"""

import argparse
import base64
import sqlite3
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Core algorithm — completely independent of DB
# ---------------------------------------------------------------------------

def compute_fingerprint_bits(embedding):
    """Compute the sign-bit fingerprint from an embedding vector.

    Returns: (base64url_string, bits_used)

    Input accepts:
        - bytes (raw float32 little-endian, as stored in sense_embedding.embed)
        - numpy ndarray
        - list of floats

    The vector is L2-normalized defensively before sign extraction so
    callers that forgot to normalize still get a stable fingerprint.
    """
    import numpy as np

    if isinstance(embedding, bytes):
        vec = np.frombuffer(embedding, dtype=np.float32)
    elif isinstance(embedding, np.ndarray):
        vec = embedding.astype(np.float32, copy=False)
    else:
        vec = np.asarray(embedding, dtype=np.float32)

    if vec.size == 0:
        raise ValueError("empty embedding")

    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm

    bits = (vec >= 0).astype("uint8")
    packed = np.packbits(bits).tobytes()
    fp = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
    return fp, int(vec.size)


def decode_fingerprint(fp):
    """Decode a base64url fingerprint string back to its underlying bytes."""
    pad_needed = (-len(fp)) % 4
    padded = fp + ("=" * pad_needed)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def hamming_distance(fp_a, fp_b):
    """Count differing bits between two fingerprints (str or bytes)."""
    if isinstance(fp_a, str):
        fp_a = decode_fingerprint(fp_a)
    if isinstance(fp_b, str):
        fp_b = decode_fingerprint(fp_b)
    if len(fp_a) != len(fp_b):
        raise ValueError(
            f"fingerprint length mismatch: {len(fp_a)} vs {len(fp_b)}"
        )
    return sum(bin(a ^ b).count("1") for a, b in zip(fp_a, fp_b))


def fingerprint_method_for(embedding_method, bits):
    """Build the fingerprint_method label."""
    return f"simhash{bits}-{embedding_method}"


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def self_test():
    import numpy as np

    print("Running compute_fingerprints self-test ...")
    np.random.seed(42)

    # Test 1: 1024-dim → 171 chars
    v = np.random.randn(1024).astype(np.float32)
    fp, bits = compute_fingerprint_bits(v)
    assert bits == 1024, f"got bits={bits}"
    assert len(fp) == 171, f"got len={len(fp)}"
    print(f"  1024-dim → {len(fp)} chars, bits={bits}  PASS")

    # Test 2: 384-dim → 64 chars
    v = np.random.randn(384).astype(np.float32)
    fp, bits = compute_fingerprint_bits(v)
    assert bits == 384
    assert len(fp) == 64, f"got len={len(fp)}"
    print(f"   384-dim → {len(fp)} chars, bits={bits}  PASS")

    # Test 3: Hamming distance of v vs v is 0
    v = np.random.randn(1024).astype(np.float32)
    fp_a, _ = compute_fingerprint_bits(v)
    fp_b, _ = compute_fingerprint_bits(v)
    assert hamming_distance(fp_a, fp_b) == 0
    print(f"  Hamming(v, v) == 0  PASS")

    # Test 4: Hamming distance of v vs -v is exactly N
    fp_neg, _ = compute_fingerprint_bits(-v)
    assert hamming_distance(fp_a, fp_neg) == 1024
    print(f"  Hamming(v, -v) == 1024  PASS")

    # Test 5: Normalization-invariant
    fp_unit, _ = compute_fingerprint_bits(v)
    fp_scaled, _ = compute_fingerprint_bits(v * 10.0)
    assert fp_unit == fp_scaled
    print(f"  scale-invariant  PASS")

    # Test 6: Method label assembly
    assert fingerprint_method_for("bge-large-en-v1", 1024) == "simhash1024-bge-large-en-v1"
    print("  method label assembly  PASS")

    print()
    print("All self-tests passed.")
    return 0


# ---------------------------------------------------------------------------
# DB queries — pending row selection with frequency priority
# ---------------------------------------------------------------------------

def materialize_pending(read_conn, embedding_method, by_frequency,
                        top_n, min_freq, limit_lemma):
    """Pull pending (wsid, embed) tuples into memory, ordered by priority."""
    print("Materializing pending rows ...")
    t0 = time.time()

    base = """
        SELECT se.wiktionary_source_id, se.embed, sl.lemma
        FROM sense_embedding se
        JOIN sgf_lexicon sl ON sl.wiktionary_source_id = se.wiktionary_source_id
        WHERE se.embedding_method = ?
          AND se.content_fingerprint IS NULL
    """
    params = [embedding_method]

    if limit_lemma:
        base += " AND LOWER(sl.lemma) = LOWER(?)"
        params.append(limit_lemma)

    if by_frequency:
        sql = f"""
            SELECT sub.wiktionary_source_id, sub.embed
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
        sql = f"SELECT wiktionary_source_id, embed FROM ({base}) ORDER BY wiktionary_source_id"

    if top_n is not None:
        sql += f" LIMIT {int(top_n)}"

    cur = read_conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    elapsed = time.time() - t0
    print(f"  {len(rows):,} rows pending ({elapsed:.1f}s)")
    return rows


def count_for_method(read_conn, embedding_method):
    cur = read_conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM sense_embedding WHERE embedding_method = ?
    """, (embedding_method,))
    total = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM sense_embedding
        WHERE embedding_method = ? AND content_fingerprint IS NOT NULL
    """, (embedding_method,))
    done = cur.fetchone()[0]
    return total, done


# ---------------------------------------------------------------------------
# Main fingerprint loop
# ---------------------------------------------------------------------------

def run_fingerprinting(db_path, embedding_method, by_frequency,
                       top_n, min_freq, limit_lemma):

    read_conn = sqlite3.connect(db_path)
    read_conn.execute("PRAGMA query_only = ON")
    write_conn = sqlite3.connect(db_path)
    write_conn.execute("PRAGMA journal_mode = WAL")
    write_conn.execute("PRAGMA synchronous = NORMAL")

    total, done = count_for_method(read_conn, embedding_method)
    print(f"Method: {embedding_method}")
    print(f"  total sense_embedding rows under method : {total:,}")
    print(f"  already fingerprinted                   : {done:,}")
    print(f"  remaining                               : {total - done:,}")
    print()

    rows = materialize_pending(
        read_conn, embedding_method, by_frequency, top_n, min_freq, limit_lemma
    )
    if not rows:
        print("Nothing to fingerprint.")
        read_conn.close()
        write_conn.close()
        return 0
    print()

    write_cur = write_conn.cursor()
    processed = 0
    t_start = time.time()
    last_report = t_start
    batch_params = []
    BATCH_SIZE = 5000

    fp_method = None  # set on first row, must be consistent
    for wsid, blob in rows:
        fp, bits = compute_fingerprint_bits(blob)
        this_fp_method = fingerprint_method_for(embedding_method, bits)
        if fp_method is None:
            fp_method = this_fp_method
            print(f"  fingerprint method: {fp_method}")
        elif this_fp_method != fp_method:
            raise RuntimeError(
                f"inconsistent fingerprint method within a single run: "
                f"{this_fp_method!r} vs {fp_method!r}. "
                f"This means embedding dim varies inside the same "
                f"embedding_method, which shouldn't happen."
            )

        batch_params.append((fp, fp_method, wsid, embedding_method))
        processed += 1

        if len(batch_params) >= BATCH_SIZE:
            write_cur.executemany("""
                UPDATE sense_embedding
                SET content_fingerprint = ?,
                    fingerprint_method = ?
                WHERE wiktionary_source_id = ? AND embedding_method = ?
            """, batch_params)
            write_conn.commit()
            batch_params = []

            now = time.time()
            if now - last_report >= 2.0:
                elapsed = now - t_start
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = len(rows) - processed
                eta_min = (remaining / rate / 60) if rate > 0 else 0
                print(f"  fingerprinted {processed:,} / {len(rows):,} "
                      f"({100.0 * processed / len(rows):.1f}%)  "
                      f"{rate:,.0f} rows/s  ETA {eta_min:.1f} min")
                last_report = now

    if batch_params:
        write_cur.executemany("""
            UPDATE sense_embedding
            SET content_fingerprint = ?,
                fingerprint_method = ?
            WHERE wiktionary_source_id = ? AND embedding_method = ?
        """, batch_params)
        write_conn.commit()

    read_conn.close()
    write_conn.close()
    return processed


# ---------------------------------------------------------------------------
# --compare: print the fingerprints of two canonical IDs side by side
# ---------------------------------------------------------------------------

def compare_two(db_path, embedding_method, cid_a, cid_b):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    rows = {}
    for cid in (cid_a, cid_b):
        cur.execute("""
            SELECT sl.canonical_id, sl.lemma, sl.microgloss, sl.gloss,
                   se.embedding_dim, se.content_fingerprint, se.fingerprint_method
            FROM sgf_lexicon sl
            JOIN sense_embedding se ON se.wiktionary_source_id = sl.wiktionary_source_id
            WHERE sl.canonical_id = ? AND se.embedding_method = ?
        """, (cid, embedding_method))
        r = cur.fetchone()
        if r is None:
            print(f"NOT FOUND: {cid} (method={embedding_method})", file=sys.stderr)
            return 1
        rows[cid] = r
    conn.close()

    a = rows[cid_a]
    b = rows[cid_b]
    print()
    print(f"A: {a[0]}")
    print(f"   lemma:      {a[1]}")
    print(f"   microgloss: {a[2]}")
    print(f"   gloss:      {a[3]}")
    print(f"   fp_method:  {a[6]}")
    print(f"   fingerprint:")
    print(f"     {a[5]}")
    print()
    print(f"B: {b[0]}")
    print(f"   lemma:      {b[1]}")
    print(f"   microgloss: {b[2]}")
    print(f"   gloss:      {b[3]}")
    print(f"   fp_method:  {b[6]}")
    print(f"   fingerprint:")
    print(f"     {b[5]}")
    print()

    if a[6] != b[6]:
        print(f"  fingerprint_method mismatch — comparison meaningless")
        return 1

    if a[5] is None or b[5] is None:
        print("  one or both fingerprints not yet computed")
        return 1

    dist = hamming_distance(a[5], b[5])
    bits = a[4]  # embedding_dim == number of bits
    print(f"  Hamming distance: {dist} of {bits} bits  "
          f"({100.0 * dist / bits:.1f}% differ)")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Compute simhash content fingerprints into sense_embedding."
    )
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--embedding-method", default=None,
                   help="Which embedder's rows to fingerprint")
    p.add_argument("--by-frequency", dest="by_frequency", action="store_true",
                   default=True)
    p.add_argument("--no-frequency", dest="by_frequency", action="store_false")
    p.add_argument("--top-n", type=int, default=None)
    p.add_argument("--min-freq", type=int, default=None)
    p.add_argument("--lemma", default=None)
    p.add_argument("--self-test", action="store_true",
                   help="Run algorithm self-test on synthetic data")
    p.add_argument("--compare", nargs=2, metavar=("CANONICAL_A", "CANONICAL_B"),
                   help="Compare fingerprints of two canonical IDs")
    args = p.parse_args()

    if args.self_test:
        return self_test()

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"Target DB not found: {db_path}", file=sys.stderr)
        return 1

    if args.compare:
        if not args.embedding_method:
            print("--compare requires --embedding-method", file=sys.stderr)
            return 1
        return compare_two(db_path, args.embedding_method,
                           args.compare[0], args.compare[1])

    if not args.embedding_method:
        print("--embedding-method is required", file=sys.stderr)
        return 1

    print(f"Target:          {db_path.resolve()}")
    print(f"Method:          {args.embedding_method}")
    print(f"By-frequency:    {args.by_frequency}")
    if args.top_n is not None:
        print(f"Top-N limit:     {args.top_n:,}")
    if args.min_freq is not None:
        print(f"Min rank cutoff: {args.min_freq:,}")
    if args.lemma:
        print(f"Lemma:           {args.lemma}")
    print()

    processed = run_fingerprinting(
        db_path=db_path,
        embedding_method=args.embedding_method,
        by_frequency=args.by_frequency,
        top_n=args.top_n,
        min_freq=args.min_freq,
        limit_lemma=args.lemma,
    )

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM sense_embedding
        WHERE embedding_method = ? AND content_fingerprint IS NOT NULL
    """, (args.embedding_method,))
    n_total = cur.fetchone()[0]
    conn.close()

    print()
    print("=" * 60)
    print("FINGERPRINT COMPUTE COMPLETE")
    print("=" * 60)
    print(f"  processed this run        : {processed:,}")
    print(f"  total fingerprinted under {args.embedding_method!r:>16}: {n_total:,}")
    print(f"  output db                 : {db_path.resolve()}")
    print()
    print("Next step (optional, after most rows have a fingerprint):")
    print(f"  python calibrate_fingerprint.py --target {db_path.name} "
          f"--embedding-method {args.embedding_method}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
