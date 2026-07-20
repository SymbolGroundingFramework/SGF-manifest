
"""lemma_resolver.py -- map surface forms (burned, running) to lemmas.

Reads the lemma_form table once at first call and caches it in RAM as
a dict[form -> list of (lemma, pos_simple, tags_list)]. Subsequent
lookups are dict-lookups.

Two public entry points:

    resolve(form, db_path)
        Returns a list of (lemma, pos_simple, tags_list) candidates,
        ordered with the most likely interpretation first (currently
        ordered by lemma frequency rank when available, else by string).

    resolve_one(form, db_path, prefer_pos=None)
        Returns a single (lemma, pos_simple, tags_list) or None.
        If prefer_pos is given, prefers that pos; otherwise picks the
        most frequent candidate.

    expand_to_lemmas(form, db_path, prefer_pos=None)
        Returns just the lemma strings (no pos, no tags), deduplicated,
        in resolution order.

    clear_cache(db_path=None)
        Drop the cached form_map. Call after rebuilding lemma_form.

The form lookup is case-insensitive. If the form IS a lemma already
(e.g. the user typed "burn", not "burned"), the resolver returns the
identity match -- callers can treat the input as both possibly a form
AND possibly a lemma.

This module never embeds and never reads synapedia_entry directly. It
only reads lemma_form (built by build_lemma_forms.py) and optionally
lemma_frequency (for ranking candidates). That keeps it cheap to
import and side-effect free.
"""
import sqlite3
import threading


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

# Map keyed by db_path -> {form_lower: [(lemma, pos_simple, tags_list), ...]}
_CACHE = {}
_CACHE_LOCK = threading.Lock()


def _load_table(conn):
    """Load lemma_form into a dict keyed by form. Returns None if the
    table does not exist (degrades silently so older DBs keep working)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='lemma_form'")
    if not cur.fetchone():
        return None

    # Optionally pull lemma_frequency for ranking. Older DBs may also
    # lack this; just fall back to alphabetical.
    cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='lemma_frequency'")
    has_freq = cur.fetchone() is not None
    freq_map = {}
    if has_freq:
        try:
            for lemma, rank in cur.execute(
                "SELECT lemma, frequency_rank FROM lemma_frequency"
            ):
                if lemma and rank is not None:
                    freq_map[lemma.lower()] = int(rank)
        except sqlite3.OperationalError:
            freq_map = {}

    out = {}
    try:
        rows = cur.execute("""
            SELECT form, lemma, pos_simple, tags_json FROM lemma_form
        """).fetchall()
    except sqlite3.OperationalError:
        return None

    import json
    for form, lemma, pos_simple, tags_json in rows:
        tags = []
        if tags_json:
            try:
                parsed = json.loads(tags_json)
                if isinstance(parsed, list):
                    tags = parsed
            except (json.JSONDecodeError, TypeError):
                pass
        out.setdefault(form, []).append((lemma, pos_simple, tags))

    # Sort each candidate list by lemma frequency rank ascending (lower
    # rank = more frequent). Lemmas not in freq_map sort to the tail.
    def sort_key(item):
        lemma = item[0]
        return freq_map.get(lemma, 10**9)

    for form in out:
        out[form].sort(key=sort_key)
    return out


def _get_cache(db_path):
    """Return the cached form_map for `db_path`, building it lazily."""
    key = str(db_path)
    with _CACHE_LOCK:
        if key not in _CACHE:
            conn = sqlite3.connect(db_path)
            try:
                _CACHE[key] = _load_table(conn) or {}
            finally:
                conn.close()
    return _CACHE[key]


def clear_cache(db_path=None):
    """Drop the cached form_map. Call after rebuilding lemma_form."""
    with _CACHE_LOCK:
        if db_path is None:
            _CACHE.clear()
        else:
            _CACHE.pop(str(db_path), None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve(form, db_path):
    """Return a list of (lemma, pos_simple, tags_list) candidates.

    If `form` is itself a lemma in the lexicon (no inflection needed),
    the identity match is included as the FIRST candidate. Inflection
    candidates follow, ordered by lemma frequency.

    Empty list when the form is unknown.
    """
    if not form:
        return []
    form_l = form.strip().lower()
    if not form_l:
        return []
    cache = _get_cache(db_path)
    out = []
    seen = set()

    # If the form matches a known lemma, treat it as itself first
    for cand_list in cache.values():
        for (lemma, pos_simple, _tags) in cand_list:
            if lemma == form_l:
                key = (lemma, pos_simple)
                if key not in seen:
                    out.append((lemma, pos_simple, ["lemma"]))
                    seen.add(key)
                break

    # Then add the form -> lemma mappings
    for (lemma, pos_simple, tags) in cache.get(form_l, []):
        key = (lemma, pos_simple)
        if key in seen:
            continue
        out.append((lemma, pos_simple, tags))
        seen.add(key)

    return out


def resolve_one(form, db_path, prefer_pos=None):
    """Return the single best (lemma, pos_simple, tags_list) or None.

    `prefer_pos` is a hint: when set, candidates with that pos_simple
    win over candidates without it. Otherwise the first candidate
    (frequency-ranked) wins.
    """
    candidates = resolve(form, db_path)
    if not candidates:
        return None
    if prefer_pos:
        for c in candidates:
            if c[1] == prefer_pos:
                return c
    return candidates[0]


def expand_to_lemmas(form, db_path, prefer_pos=None):
    """Return just the lemma strings (no pos, no tags), deduplicated,
    in resolution order. Handy for `--lemma-restrict` callers that
    accept multiple lemmas."""
    seen = set()
    out = []
    for (lemma, pos_simple, _tags) in resolve(form, db_path):
        if prefer_pos and pos_simple != prefer_pos:
            continue
        if lemma in seen:
            continue
        seen.add(lemma)
        out.append(lemma)
    return out
