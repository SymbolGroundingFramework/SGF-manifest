#!/usr/bin/env python3
"""
select_standard_forms.py -- Stage 10 -- standard-form selection

For every content_identical_group that has no standard_form_wsid set,
pick the member to designate as the standard form. The standard form
is the unmarked, contemporary, central representative of the group.

WHY THIS EXISTS
---------------
A content_identical_group with no standard form cannot drive the
snap_to_standard retrieval policy. Every group must have exactly one
standard form. Standard-form selection is a judgment call that
combines metadata filtering (register/temporal/social) with semantic
centrality (cosine distance to group centroid) and is finalized by
an LLM that sees the full group and picks the best representative.

ALGORITHM
---------
1. Metadata filter:
     - prefer register='neutral' over slang/poetic/formal
     - prefer temporal_status='live' over dated/archaic/obsolete
     - prefer social_status='unmarked' over flagged/offensive/slur
   If the metadata filter leaves exactly one candidate, that wins
   and the LLM is skipped (selection_method='metadata_filter').

2. Centroid distance (tie-break input):
     - For LLM-ambiguous cases, the candidate closest to the group
       centroid is provided as the "centroid pick" hint.

3. LLM judgment:
     - Send the group, the metadata-shortlisted candidates, and the
       centroid pick to the LLM. LLM returns one winner.
     - selection_method='llm_judgment'.

USAGE
-----
    python select_standard_forms.py --target sgf_lexicon.db \\
        --embedding-method bge-large-en-v1 \\
        --llm-wrapper /path/to/llm.py \\
        [--limit 1000] [--dry-run]

NOTES
-----
- Metadata-only winners are written immediately without LLM call.
- LLM call uses the same wrapper contract as improve_microgloss.py.
- Output rationale is stored in content_identical_group.rationale.
"""

from __future__ import annotations

import argparse
import llm_kv_parser as kv
import os
import secrets
import tempfile
import sqlite3
import struct
import subprocess
import sys
import time
from pathlib import Path


REGISTER_PREF = {
    "neutral": 0, "formal": 1, "affectionate": 2, "informal": 2,
    "poetic": 3, "literary": 3, "slang": 4, "vulgar": 5, "academic": 1,
}
TEMPORAL_PREF = {"live": 0, "revived": 1, "dated": 2, "archaic": 3, "obsolete": 4}
SOCIAL_PREF = {
    "unmarked": 0, "informal_only": 1, "dated": 1, "flagged": 2,
    "offensive": 3, "slur": 4,
}


def vector_from_blob(blob):
    if blob is None:
        return None
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def centroid(vecs):
    n = len(vecs)
    d = len(vecs[0])
    c = [0.0] * d
    for v in vecs:
        for i in range(d):
            c[i] += v[i]
    norm = 0.0
    for i in range(d):
        c[i] /= n
        norm += c[i] * c[i]
    norm = norm ** 0.5
    if norm > 0:
        for i in range(d):
            c[i] /= norm
    return c


def cosine_norm(a, b):
    s = 0.0
    for x, y in zip(a, b):
        s += x * y
    return s


def metadata_score(member):
    """Lower is better."""
    return (
        REGISTER_PREF.get(member["register"] or "neutral", 9),
        TEMPORAL_PREF.get(member["temporal_status"] or "live", 9),
        SOCIAL_PREF.get(member["social_status"] or "unmarked", 9),
    )


def call_llm(llm_wrapper, prompt, tier="flash", temp=0.0, timeout_seconds=120):
    tmp = Path(tempfile.gettempdir())
    tag = f"{os.getpid()}_{secrets.token_hex(4)}"
    in_file = tmp / f"sfs_in_{tag}.txt"
    out_file = tmp / f"sfs_out_{tag}.txt"
    try:
        in_file.write_text(prompt, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(llm_wrapper),
             "--in-file", str(in_file), "--out-file", str(out_file),
             "--tier", tier, "--temp", str(temp)],
            capture_output=True, text=True, timeout=timeout_seconds,
        )
        if result.returncode != 0 or not out_file.exists():
            return None
        return out_file.read_text(encoding="utf-8")
    except (subprocess.TimeoutExpired, OSError, UnicodeDecodeError):
        return None
    finally:
        try:
            in_file.unlink(missing_ok=True)
            out_file.unlink(missing_ok=True)
        except OSError:
            pass


SYSTEM_PROMPT = """\
You are picking the STANDARD FORM for a group of content-identical
senses in a multilingual lexicon. The standard form is the unmarked,
contemporary, central representative -- the form you would default
to in unmarked retrieval.

You will see a group of senses that share content meaning at the
'general' audience tier. They differ in register, temporal status,
social status, or stylistic markedness. Your job is to pick ONE
member as the standard form.

Prefer (in order):
  1. register='neutral' over slang/poetic/formal
  2. temporal_status='live' over dated/archaic/obsolete
  3. social_status='unmarked' over flagged/offensive/slur
  4. higher lemma frequency
  5. shorter, simpler microgloss
  6. semantic centrality (closer to group centroid)

WRAP YOUR ANSWER IN TAGS
------------------------
Put the structured answer inside <answer>...</answer>. Put any
reasoning, caveats, or commentary inside <comments>...</comments>.
The downstream parser only reads what is inside <answer>.

The answer block format is:

  <answer>
  STANDARD_FORM
  chosen_wsid: <integer wsid of the chosen member>
  rationale: <one sentence explaining the choice>
  </answer>

NO JSON. NO CODE FENCES.
"""


def build_prompt(group_id, members, centroid_pick_wsid):
    lines = [SYSTEM_PROMPT, "", f"GROUP_ID: {group_id}", "MEMBERS:"]
    for m in members:
        lines.append(
            f"  wsid={m['wsid']} lemma={m['lemma']!r} "
            f"canonical_id={m['canonical_id']!r} "
            f"register={m['register']} "
            f"temporal={m['temporal_status']} "
            f"social={m['social_status']} "
            f"centroid_dist={m.get('centroid_dist', 'NA')}"
        )
    lines.append("")
    lines.append(f"CENTROID PICK (closest to centroid): {centroid_pick_wsid}")
    lines.append("")
    lines.append("Emit your reply now. Wrap the answer block in <answer>...</answer>.")
    return "\n".join(lines)


def parse_response(raw):
    """Two-layer parse: <answer> envelope, then KV block.

    Returns a dict with 'chosen_wsid' (int) and 'rationale' (str), or
    None if the response was unparseable.
    """
    blocks = kv.parse_llm_response(raw)
    if not blocks:
        return None
    # Take the first block that has chosen_wsid
    for b in blocks:
        chosen = kv.as_int(b.get("chosen_wsid"))
        if chosen is not None:
            return {
                "chosen_wsid": chosen,
                "rationale": (b.get("rationale") or "").strip(),
            }
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--embedding-method", required=True)
    p.add_argument("--llm-wrapper",
                   help="Path to LLM wrapper (only needed when metadata is ambiguous)")
    p.add_argument("--tier", default="flash")
    p.add_argument("--temp", type=float, default=0.0)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 60000")

    print(f"Target:             {db_path.resolve()}")
    print(f"Embedding method:   {args.embedding_method}")

    # Find groups needing standard-form selection
    cur = conn.execute(
        """
        SELECT group_id, audience_tier
          FROM content_identical_group
         WHERE standard_form_wsid IS NULL
        """
    )
    groups = cur.fetchall()
    if args.limit is not None:
        groups = groups[: args.limit]
    print(f"Groups needing standard form: {len(groups):,}")

    n_meta_wins = 0
    n_llm_wins = 0
    n_llm_fail = 0
    t0 = time.time()
    for idx, (gid, tier) in enumerate(groups, 1):
        cur_m = conn.execute(
            """
            SELECT cim.wsid, sl.lemma, sl.canonical_id, sl.microgloss,
                   sl.register, sl.temporal_status, sl.social_status,
                   se.embed
              FROM content_identical_member cim
              JOIN sgf_lexicon sl ON sl.wiktionary_source_id = cim.wsid
              LEFT JOIN sense_embedding se
                ON se.wiktionary_source_id = cim.wsid
               AND se.embedding_method = ?
             WHERE cim.group_id = ?
            """,
            (args.embedding_method, gid),
        )
        members = []
        for r in cur_m:
            v = vector_from_blob(r[7])
            members.append({
                "wsid": r[0], "lemma": r[1], "canonical_id": r[2],
                "microgloss": r[3], "register": r[4],
                "temporal_status": r[5], "social_status": r[6],
                "vector": v,
            })
        if len(members) < 2:
            continue

        # Centroid pick
        vecs = [m["vector"] for m in members if m["vector"] is not None]
        if vecs:
            c = centroid(vecs)
            for m in members:
                if m["vector"] is not None:
                    m["centroid_dist"] = round(1.0 - cosine_norm(c, m["vector"]), 4)
                else:
                    m["centroid_dist"] = None
            members_with_vec = [m for m in members if m["vector"] is not None]
            members_with_vec.sort(key=lambda m: m["centroid_dist"])
            centroid_pick = members_with_vec[0]["wsid"] if members_with_vec else None
        else:
            centroid_pick = None
            for m in members:
                m["centroid_dist"] = None

        # Metadata filter
        scored = sorted(members, key=metadata_score)
        best_score = metadata_score(scored[0])
        top_meta = [m for m in scored if metadata_score(m) == best_score]

        chosen_wsid = None
        method = None
        rationale = None
        if len(top_meta) == 1:
            chosen_wsid = top_meta[0]["wsid"]
            method = "metadata_filter"
            rationale = (
                f"unique unmarked candidate (register={top_meta[0]['register']}, "
                f"temporal={top_meta[0]['temporal_status']}, "
                f"social={top_meta[0]['social_status']})"
            )
            n_meta_wins += 1
        elif args.llm_wrapper:
            prompt = build_prompt(gid, top_meta, centroid_pick)
            raw = call_llm(args.llm_wrapper, prompt, args.tier, args.temp)
            resp = parse_response(raw) if raw else None
            if resp and "chosen_wsid" in resp:
                try:
                    chosen_wsid = int(resp["chosen_wsid"])
                    method = "llm_judgment"
                    rationale = str(resp.get("rationale", ""))[:500]
                    n_llm_wins += 1
                except (TypeError, ValueError):
                    n_llm_fail += 1
            else:
                n_llm_fail += 1
            # Last-ditch fallback: centroid pick
            if chosen_wsid is None and centroid_pick is not None:
                chosen_wsid = centroid_pick
                method = "centroid_fallback"
                rationale = "LLM judgment unavailable; fell back to centroid pick"
        else:
            # No LLM available -- pick the centroid-closest among metadata top set
            if top_meta and any(m["centroid_dist"] is not None for m in top_meta):
                top_meta_v = [m for m in top_meta if m["centroid_dist"] is not None]
                top_meta_v.sort(key=lambda m: m["centroid_dist"])
                chosen_wsid = top_meta_v[0]["wsid"]
                method = "centroid_fallback"
                rationale = "no LLM wrapper provided; chose closest to centroid"
            else:
                chosen_wsid = top_meta[0]["wsid"]
                method = "first_by_metadata"
                rationale = "no LLM wrapper, no embeddings; chose first by metadata"

        if chosen_wsid is None:
            continue

        if args.dry_run:
            print(
                f"  [dry] group={gid} chosen={chosen_wsid} "
                f"method={method} rationale={rationale!r}"
            )
            continue

        conn.execute(
            """
            UPDATE content_identical_group
               SET standard_form_wsid = ?,
                   selection_method = ?,
                   rationale = COALESCE(rationale, '') || ' | ' || ?,
                   standard_chosen_at = ?
             WHERE group_id = ?
            """,
            (chosen_wsid, method, rationale or "", int(time.time()), gid),
        )

        if idx % 100 == 0:
            conn.commit()
            elapsed = time.time() - t0
            rate = idx / max(elapsed, 0.001)
            remain = (len(groups) - idx) / max(rate, 0.001)
            print(
                f"  [{idx}/{len(groups)}] meta={n_meta_wins} "
                f"llm={n_llm_wins} fail={n_llm_fail}  "
                f"{rate:.2f}/s  eta={remain/60:.1f}m"
            )
    conn.commit()

    print()
    print("=" * 60)
    print("STANDARD-FORM SELECTION COMPLETE")
    print("=" * 60)
    print(f"  groups processed:        {len(groups):,}")
    print(f"  metadata-only winners:   {n_meta_wins:,}")
    print(f"  LLM-judgment winners:    {n_llm_wins:,}")
    print(f"  LLM failures (fallback): {n_llm_fail:,}")
    print(f"  elapsed:                 {(time.time()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
