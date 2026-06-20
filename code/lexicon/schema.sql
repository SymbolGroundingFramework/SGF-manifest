-- =========================================================================
-- schema.sql
--
-- SGF lexicon schema. Single source of truth.
--
-- Idempotent. Safe to run on a fresh DB or on an existing DB.
--
-- USAGE:
--   sqlite3 sgf_lexicon.db < schema.sql
-- =========================================================================

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- -------------------------------------------------------------------------
-- sgf_lexicon -- one row per sense
--
-- This is the parent table for every sense the pipeline knows about.
-- Embeddings live in sense_embedding (child); semantic relations live in
-- sense_relation. The columns below are the stable surface of a sense.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sgf_lexicon (
    wiktionary_source_id           INTEGER PRIMARY KEY,
    lemma                          TEXT    NOT NULL,

    -- Part-of-speech (three views: raw Wiktionary, spaCy-normalized, SGF-simple)
    pos_wiktionary                 TEXT    NOT NULL,
    pos_spacy                      TEXT    NOT NULL,
    pos_simple                     TEXT    NOT NULL,

    -- Original Wiktionary gloss (first gloss only; full list in wiktionary_source)
    gloss                          TEXT    NOT NULL,

    -- Filled by Stage 3 (generate_microglosses.py)
    microgloss                     TEXT,
    microgloss_version             TEXT,
    canonical_id                   TEXT UNIQUE,
    namespace                      TEXT,
    iso_lang                       TEXT,

    -- Provisional values preserved after the improver writes the live ones
    microgloss_provisional         TEXT,
    canonical_id_provisional       TEXT,

    -- Metadata (harvested from Wiktionary tags, refined by the improver)
    register                       TEXT,
    temporal_status                TEXT,
    social_status                  TEXT,
    specificity                    TEXT,         -- general / specialist / technical
    sparse_data_flag               INTEGER NOT NULL DEFAULT 0,

    -- Maturity tier (pipeline progress for this sense)
    maturity_tier                  TEXT    NOT NULL DEFAULT 'raw',

    -- Embedding text (single-pass legacy field, used by older scripts)
    embedding_text                 TEXT,
    embedding_text_version         TEXT,

    -- Two-pass embedding text (v1 = diagnostic bge-small; v2 = production bge-large)
    embedding_text_v1              TEXT,
    embedding_text_v1_version      TEXT,
    embedding_text_v1_built_at     INTEGER,
    embedding_text_v2              TEXT,
    embedding_text_v2_version      TEXT,
    embedding_text_v2_built_at     INTEGER,
    embedding_text_needs_rebuild   INTEGER NOT NULL DEFAULT 1,

    -- Bookkeeping
    minted_at                      INTEGER,
    created_at                     INTEGER,
    updated_at                     INTEGER,

    FOREIGN KEY (wiktionary_source_id)
        REFERENCES wiktionary_source(source_sense_id)
);

CREATE INDEX IF NOT EXISTS idx_sgf_lemma            ON sgf_lexicon(lemma);
CREATE INDEX IF NOT EXISTS idx_sgf_lemma_pos        ON sgf_lexicon(lemma, pos_simple);
CREATE INDEX IF NOT EXISTS idx_sgf_lemma_spacy      ON sgf_lexicon(lemma, pos_spacy);
CREATE INDEX IF NOT EXISTS idx_sgf_canonical_id     ON sgf_lexicon(canonical_id);
CREATE INDEX IF NOT EXISTS idx_sgf_register         ON sgf_lexicon(register);
CREATE INDEX IF NOT EXISTS idx_sgf_temporal         ON sgf_lexicon(temporal_status);
CREATE INDEX IF NOT EXISTS idx_sgf_social           ON sgf_lexicon(social_status);
CREATE INDEX IF NOT EXISTS idx_sgf_specificity      ON sgf_lexicon(specificity);
CREATE INDEX IF NOT EXISTS idx_sgf_maturity         ON sgf_lexicon(maturity_tier);
CREATE INDEX IF NOT EXISTS idx_sgf_sparse           ON sgf_lexicon(sparse_data_flag) WHERE sparse_data_flag = 1;
CREATE INDEX IF NOT EXISTS idx_sgf_needs_rebuild    ON sgf_lexicon(embedding_text_needs_rebuild) WHERE embedding_text_needs_rebuild = 1;

-- -------------------------------------------------------------------------
-- sense_embedding -- one row per (sense, embedder method)
--
-- Embeddings and content fingerprints live here. Multiple embedders can
-- coexist for the same sense (bge-small, bge-large, bge-m3).
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sense_embedding (
    wiktionary_source_id   INTEGER NOT NULL,
    embedding_method       TEXT    NOT NULL,
    embedding_dim          INTEGER NOT NULL,
    embed                  BLOB    NOT NULL,
    content_fingerprint    TEXT,
    fingerprint_method     TEXT,
    computed_at            INTEGER NOT NULL,
    PRIMARY KEY (wiktionary_source_id, embedding_method)
);

CREATE INDEX IF NOT EXISTS idx_se_method
    ON sense_embedding(embedding_method);

CREATE INDEX IF NOT EXISTS idx_se_method_fp
    ON sense_embedding(embedding_method, content_fingerprint);

CREATE INDEX IF NOT EXISTS idx_se_pending_fp
    ON sense_embedding(wiktionary_source_id, embedding_method)
    WHERE content_fingerprint IS NULL;

-- -------------------------------------------------------------------------
-- sense_enrichment -- improver output, one row per (sense, run)
--
-- Each row is one pass of the LLM improvement stage. The PK separates
-- multiple enrichment runs for the same sense.
--
-- Note: the wsid column is named source_sense_id here (not
-- wiktionary_source_id) to match the existing improve_microgloss.py
-- and downstream readers. Same integer, different name.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sense_enrichment (
    source_sense_id             INTEGER NOT NULL,
    enrichment_version          TEXT    NOT NULL,
    model                       TEXT,
    prompt_version              TEXT,
    improved_microgloss         TEXT,
    improved_definition         TEXT,
    register                    TEXT,
    temporal_status             TEXT,
    social_status               TEXT,
    social_notes                TEXT,
    domain                      TEXT,
    biographical_metadata_json  TEXT,
    rationale                   TEXT,
    created_at                  INTEGER NOT NULL,
    PRIMARY KEY (source_sense_id, enrichment_version)
);

CREATE INDEX IF NOT EXISTS idx_enrichment_version
    ON sense_enrichment(enrichment_version);

-- -------------------------------------------------------------------------
-- sense_relation -- semantic relations between senses
--
-- Covers IS_A, HAS_PART, and the 15 SGF roles, plus cousin classifications
-- from the improver. interchangeable_* flags drive the snap-to-standard
-- policy at lookup time.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sense_relation (
    source_wsid                              INTEGER NOT NULL,
    target_wsid                              INTEGER NOT NULL,
    relation_type                            TEXT NOT NULL,
    interchangeable_intra_language           INTEGER NOT NULL DEFAULT 0,
    interchangeable_cross_language_standard  INTEGER NOT NULL DEFAULT 0,
    interchangeable_cross_language_preserve  INTEGER NOT NULL DEFAULT 0,
    relation_note                            TEXT,
    source_method                            TEXT NOT NULL,
    created_at                               INTEGER NOT NULL,
    PRIMARY KEY (source_wsid, target_wsid, source_method)
);

CREATE INDEX IF NOT EXISTS idx_sr_source             ON sense_relation(source_wsid);
CREATE INDEX IF NOT EXISTS idx_sr_target             ON sense_relation(target_wsid);
CREATE INDEX IF NOT EXISTS idx_sr_type               ON sense_relation(relation_type);
CREATE INDEX IF NOT EXISTS idx_sr_interchange_intra  ON sense_relation(source_wsid, interchangeable_intra_language);

-- -------------------------------------------------------------------------
-- lemma_frequency -- priority ranking for frontier expansion
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lemma_frequency (
    lemma            TEXT PRIMARY KEY,
    frequency_rank   INTEGER,
    frequency_count  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_lf_rank ON lemma_frequency(frequency_rank);

-- -------------------------------------------------------------------------
-- frontier_run -- audit log of every orchestrator run
--
-- run_frontier.py writes one row per invocation. config_toml stores the
-- exact TOML config that drove the run (as JSON for portability) so a
-- later audit can reproduce the run conditions.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS frontier_run (
    run_id          TEXT    PRIMARY KEY,
    config_name     TEXT    NOT NULL,
    config_toml     TEXT    NOT NULL,
    started_at      INTEGER NOT NULL,
    completed_at    INTEGER,
    target_tier     TEXT    NOT NULL,
    scope_summary   TEXT,
    stages_ran      TEXT,
    status          TEXT    NOT NULL,        -- 'running' / 'completed' / 'failed'
    n_promoted      INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_frontier_started ON frontier_run(started_at);
CREATE INDEX IF NOT EXISTS idx_frontier_status  ON frontier_run(status);

-- -------------------------------------------------------------------------
-- content_identical_group -- one row per cluster of senses with the same
-- meaning at a given audience tier. Standard-form selection lives here.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS content_identical_group (
    group_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    audience_tier       TEXT NOT NULL DEFAULT 'general',
    standard_form_wsid  INTEGER,
    selection_method    TEXT,
    centroid_distance   REAL,
    rationale           TEXT,
    discovered_at       INTEGER NOT NULL,
    standard_chosen_at  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_cig_standard ON content_identical_group(standard_form_wsid);
CREATE INDEX IF NOT EXISTS idx_cig_tier     ON content_identical_group(audience_tier);

-- -------------------------------------------------------------------------
-- content_identical_member -- one row per (group, sense) membership.
-- A single sense can belong to multiple groups across audience_tiers.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS content_identical_member (
    group_id    INTEGER NOT NULL,
    wsid        INTEGER NOT NULL,
    added_at    INTEGER NOT NULL,
    add_method  TEXT NOT NULL,
    confidence  REAL,
    PRIMARY KEY (group_id, wsid),
    FOREIGN KEY (group_id) REFERENCES content_identical_group(group_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cim_wsid  ON content_identical_member(wsid);
CREATE INDEX IF NOT EXISTS idx_cim_group ON content_identical_member(group_id);

-- -------------------------------------------------------------------------
-- sense_semantic_relation -- IS_A, HAS_PART, and the 15 SGF roles
--
-- Distinct from sense_relation: this table holds ontological /
-- compositional / role edges from Stage 11. sense_relation holds the
-- cousin-classification edges (synonym / near_synonym / cohyponym /
-- embedder_noise / unrelated) from the improver.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sense_semantic_relation (
    ssr_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    source_wsid               INTEGER NOT NULL,
    relation_type             TEXT    NOT NULL,   -- IS_A, HAS_PART, HAS_AGENT, ...
    relation_kind             TEXT    NOT NULL,   -- ontological / core_role / context_role
    target_wsid               INTEGER,            -- nullable: target may be a placeholder
    target_placeholder        TEXT,               -- raw LLM target lemma if not resolved
    target_microgloss_hint    TEXT,               -- LLM's description of the target meaning
    target_canonical_id_guess TEXT,               -- LLM's guessed canonical_id string
    target_resolution_method  TEXT,               -- 'embed_filter_v1' / 'lemma_only' / 'unresolved' / 'pattern_v1'
    target_resolution_cosine  REAL,               -- cosine sim of the resolved match (proxy for confidence)
    confidence                REAL    NOT NULL,
    source_method             TEXT    NOT NULL,   -- 'wiktionary_pattern' / 'llm' / etc.
    llm_model                 TEXT,
    rationale                 TEXT,
    created_at                INTEGER NOT NULL,
    UNIQUE (source_wsid, relation_type, target_wsid, target_placeholder, source_method)
);

CREATE INDEX IF NOT EXISTS idx_ssr_source ON sense_semantic_relation(source_wsid);
CREATE INDEX IF NOT EXISTS idx_ssr_target ON sense_semantic_relation(target_wsid);
CREATE INDEX IF NOT EXISTS idx_ssr_type   ON sense_semantic_relation(relation_type);
CREATE INDEX IF NOT EXISTS idx_ssr_kind   ON sense_semantic_relation(relation_kind);

-- -------------------------------------------------------------------------
-- quality_audit -- one row per sense per audit pass.
--
-- Captures top-K self-retrieval results, the relaxed and strict pass
-- verdicts, and the rank at which the sense found itself. Stages 5.5
-- and 8.5 populate this; the ship gate is 99% relaxed pass rate.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quality_audit (
    audit_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    wsid                      INTEGER NOT NULL,
    audit_run_id              TEXT    NOT NULL,    -- e.g. 'pass_v1_2026_06_10'
    audit_phase               TEXT    NOT NULL,    -- 'first_pass' / 'production' / 'rebuild'
    embedding_method          TEXT    NOT NULL,
    self_rank                 INTEGER,             -- 1 = top-1
    top_k_canonical_ids_json  TEXT    NOT NULL,
    top_k_distances_json      TEXT    NOT NULL,
    strict_pass               INTEGER NOT NULL,    -- self at top-1
    relaxed_pass              INTEGER NOT NULL,    -- self or content-identical at top-1
    reason                    TEXT,
    audited_at                INTEGER NOT NULL,
    UNIQUE (wsid, audit_run_id)
);

CREATE INDEX IF NOT EXISTS idx_qa_wsid    ON quality_audit(wsid);
CREATE INDEX IF NOT EXISTS idx_qa_run     ON quality_audit(audit_run_id);
CREATE INDEX IF NOT EXISTS idx_qa_phase   ON quality_audit(audit_phase);
CREATE INDEX IF NOT EXISTS idx_qa_strict  ON quality_audit(strict_pass);
CREATE INDEX IF NOT EXISTS idx_qa_relaxed ON quality_audit(relaxed_pass);

-- -------------------------------------------------------------------------
-- cluster_discovery_progress -- resumable cluster discovery (Stage 9)
--
-- One row per (seed, discovery_run) pair. discover_clusters.py uses
-- this to skip seeds already processed in the current run, enabling
-- resume-from-crash without re-walking finished seeds.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cluster_discovery_progress (
    wsid               INTEGER NOT NULL,
    discovery_run_id   TEXT    NOT NULL,
    processed_at       INTEGER NOT NULL,
    cluster_count      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (wsid, discovery_run_id)
);

CREATE INDEX IF NOT EXISTS idx_cdp_run ON cluster_discovery_progress(discovery_run_id);

-- -------------------------------------------------------------------------
-- microgloss_assignment -- one row per microgloss assignment attempt.
--
-- Records the provenance of every microgloss the deterministic
-- iterative generator (iterate_microglosses.py) assigns. Kept separate
-- from sgf_lexicon so reassignment history survives an embedder upgrade
-- and so the (sometimes fat) tournament_candidates_json blob does not
-- bloat the main table.
--
-- Lookup pattern for "current assignment for this sense":
--   SELECT * FROM microgloss_assignment
--    WHERE wsid = ? AND superseded_by IS NULL
--   ORDER BY assigned_at DESC LIMIT 1
--
-- When a sense is reassigned, the new row is written with
-- superseded_by = NULL and the previous row's superseded_by is set to
-- the new row's assignment_id. This keeps the history intact.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS microgloss_assignment (
    assignment_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    wsid                       INTEGER NOT NULL,
    microgloss                 TEXT    NOT NULL,
    strategy                   TEXT    NOT NULL,
        -- one of: compositional, lemma_mate_disambig, cluster_anchor,
        -- tag_qualified, example_distilled, antonym_contrast,
        -- hypernym_specialized, definitional_fallback, llm_improver
    audit_t1_passed            INTEGER NOT NULL,    -- 0/1
    audit_t1_rank              INTEGER,             -- 1 = top in lemma-filtered
    audit_t1_margin            REAL,                -- score gap top-1 vs top-2
    audit_t2_passed            INTEGER NOT NULL,    -- 0/1
    audit_t2_rank              INTEGER,             -- rank within cluster
    audit_t2_cluster_size      INTEGER,
    audit_t2_quantile          REAL,                -- 0.0 best, 1.0 worst
    polysemy_tier              TEXT,                -- low|medium|high|very_high
    tournament_candidates_json TEXT,                -- [{strategy, mg, m1, m2, score}]
    n_strategies_tried         INTEGER,
    assigned_at                INTEGER NOT NULL,
    embedder_at_assignment     TEXT,                -- which embedder gated the audit
    superseded_by              INTEGER,             -- FK to a later assignment_id
    FOREIGN KEY (superseded_by)
        REFERENCES microgloss_assignment(assignment_id)
);

CREATE INDEX IF NOT EXISTS idx_ma_wsid       ON microgloss_assignment(wsid);
CREATE INDEX IF NOT EXISTS idx_ma_current    ON microgloss_assignment(wsid)
    WHERE superseded_by IS NULL;
CREATE INDEX IF NOT EXISTS idx_ma_strategy   ON microgloss_assignment(strategy);
CREATE INDEX IF NOT EXISTS idx_ma_t1_passed  ON microgloss_assignment(audit_t1_passed);
CREATE INDEX IF NOT EXISTS idx_ma_t2_passed  ON microgloss_assignment(audit_t2_passed);
CREATE INDEX IF NOT EXISTS idx_ma_tier       ON microgloss_assignment(polysemy_tier);

-- -------------------------------------------------------------------------
-- lemma_form -- inflected-form to lemma resolution.
--
-- Maps surface forms (burned, running, geese) to their lemma (burn,
-- run, goose). Populated from wiktionary_source.forms_json by
-- build_lemma_forms.py. Used by search-side query preprocessing so
-- that `--lemma-restrict burned` resolves to all senses of `burn`.
--
-- A single form may map to multiple lemmas across parts of speech
-- ("saw" can be past-of-see, present-of-saw-tool, or a noun for the
-- tool itself). One row per (form, lemma, pos_simple) triple captures
-- that ambiguity; resolution callers pick by preferred pos or take
-- all.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lemma_form (
    form           TEXT    NOT NULL,    -- inflected surface form (lowercased)
    lemma          TEXT    NOT NULL,    -- canonical lemma (lowercased)
    pos_simple     TEXT    NOT NULL,    -- 'n' | 'v' | 'adj' | 'adv' | 'name' | ...
    tags_json      TEXT,                -- e.g. ["past", "participle"]
    source_entry_id INTEGER,            -- back-reference for debugging
    PRIMARY KEY (form, lemma, pos_simple)
);

CREATE INDEX IF NOT EXISTS idx_lemma_form_form ON lemma_form(form);
CREATE INDEX IF NOT EXISTS idx_lemma_form_lemma ON lemma_form(lemma);

COMMIT;

ANALYZE;
