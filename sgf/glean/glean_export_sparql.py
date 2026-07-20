#!/usr/bin/env python3
"""
glean_export_sparql.py — Export the SGF Synapse Store to RDF (Turtle / SPARQL INSERT)

Two-pass export: Pass 1 creates entity/synapse/group/literal nodes (TBox).
Pass 2 creates all edges (binary core, spokes, links, groups, instances, attributes, aliases, entry-to-event links).
Includes referenced core lexicon entries up to configurable IS-A parent depth.

Usage:
    python glean_export_sparql.py \\
        --input doc.synapse_store.db \\
        --main-lexicon synapedia.db \\
        --parent-depth 1 \\
        --output doc.ttl \\
        --format turtle

    python glean_export_sparql.py \\
        --input doc.synapse_store.db \\
        --main-lexicon synapedia.db \\
        --parent-depth 1 \\
        --output doc.sparql \\
        --format sparql-insert
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------
NS = {
    "rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl":  "http://www.w3.org/2002/07/owl#",
    "syn":  "http://synapedia.org/ontology/",
    "bfo":  "http://purl.obolibrary.org/obo/BFO_",
    "xsd":  "http://www.w3.org/2001/XMLSchema#",
}

# BFO category IRI mapping
BFO_MAP = {
    "material_entity":  "bfo:BFO_0000040",
    "object":           "bfo:BFO_0000030",
    "object_aggregate": "bfo:BFO_0000027",
    "site":             "bfo:BFO_0000141",
    "process":          "bfo:BFO_0000015",
    "quality":          "bfo:BFO_0000019",
    "role":             "bfo:BFO_0000023",
    "disposition":      "bfo:BFO_0000016",
    "function":         "bfo:BFO_0000034",
    "gdc":              "bfo:BFO_0000031",
}

# Thematic roles → RDF predicates
ROLE_PREDICATE = {
    "HAS_AGENT":        "syn:hasAgent",
    "HAS_PATIENT":      "syn:hasPatient",
    "HAS_THEME":        "syn:hasTheme",
    "HAS_EXPERIENCER":  "syn:hasExperiencer",
    "HAS_RECIPIENT":    "syn:hasRecipient",
    "HAS_BENEFICIARY":  "syn:hasBeneficiary",
    "HAS_TIME":         "syn:hasTime",
    "HAS_LOCATION":     "syn:hasLocation",
    "HAS_SOURCE":       "syn:hasSource",
    "HAS_DESTINATION":  "syn:hasDestination",
    "HAS_MANNER":       "syn:hasManner",
    "HAS_INSTRUMENT":   "syn:hasInstrument",
    "HAS_CAUSE":        "syn:hasCause",
    "HAS_REASON":       "syn:hasReason",
    "HAS_ATTRIBUTE":    "syn:hasAttribute",
}

# Link types → RDF predicates
LINK_PREDICATE = {
    "PRECEDES":      "syn:precedes",
    "CAUSES":        "syn:causes",
    "ENABLES":       "syn:enables",
    "SUPPORTS":      "syn:supports",
    "CONTRADICTS":   "syn:contradicts",
    "ELABORATES":    "syn:elaborates",
    "SUPERSEDES":    "syn:supersedes",
    "DEPENDS_ON":    "syn:dependsOn",
    "SAME_AS":       "owl:sameAs",
    "SIMILAR_TO":    "syn:similarTo",
    "BROADER_THAN":  "syn:broaderThan",
    "NARROWER_THAN": "syn:narrowerThan",
    "MEMBER_OF":     "syn:memberOf",
}

# BFO dependence relation mapping
DEPENDENCE_PREDICATE = {
    "inheres_in":                "bfo:BFO_0000051",
    "realizes":                  "bfo:BFO_0000055",
    "concretizes":               "bfo:BFO_0000059",
    "specifically_depends_on":   "bfo:BFO_0000088",
    "generically_depends_on":    "bfo:BFO_0000089",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def escape_ntriple(s):
    """Escape a string literal for Turtle/SPARQL."""
    if s is None:
        return ""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")

def canonical_id_to_iri(canonical_id):
    """Map a Synapedia canonical ID to a prefixed IRI."""
    if canonical_id is None:
        return None
    if canonical_id.startswith("lit."):
        parts = canonical_id.split(".")
        return f"syn:Literal_{parts[1]}_{parts[2]}"
    if canonical_id.startswith("inst."):
        safe = canonical_id.replace(".", "_")
        return f"syn:Instance_{safe}"
    if canonical_id.startswith("ghost."):
        safe = canonical_id.replace(".", "_")
        return f"syn:Ghost_{safe}"
    if canonical_id.startswith("en."):
        safe = canonical_id.replace(".", "_")
        return f"syn:{safe}"
    # Fallback
    safe = canonical_id.replace(".", "_")
    return f"syn:{safe}"

def bfo_category_to_iri(bfo_cat):
    """Map BFO category string to IRI, or return owl:Thing."""
    if bfo_cat in BFO_MAP:
        return BFO_MAP[bfo_cat]
    return "owl:Thing"

# ---------------------------------------------------------------------------
# Main exporter class
# ---------------------------------------------------------------------------

class SparqlExporter:
    def __init__(self, synapse_db, main_lexicon_db, custom_db=None,
                 parent_depth=1, include_ghosts=False, graph_iri=None):
        self.syn_db_path = synapse_db
        self.lex_db_path = main_lexicon_db
        self.custom_db_path = custom_db
        self.parent_depth = parent_depth
        self.include_ghosts = include_ghosts
        self.graph_iri = graph_iri or self._default_graph_iri()

    def _default_graph_iri(self):
        conn = sqlite3.connect(self.syn_db_path)
        cur = conn.cursor()
        cur.execute("SELECT doc_id FROM document LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row:
            return f"syn:graph/{row[0]}"
        return "syn:graph/default"

    # -----------------------------------------------------------------------
    # Pass 1: TBox / Nodes
    # -----------------------------------------------------------------------

    def export_pass1(self):
        lines = []
        syn_conn = sqlite3.connect(self.syn_db_path)
        syn_conn.row_factory = sqlite3.Row
        syn_cur = syn_conn.cursor()

        # Used to collect parent CIDs for later node export (from lexicon)
        parent_cids = set()

        # 1a. Entities from synapse store
        syn_cur.execute("""
            SELECT ent_id, preferred_canonical, lexicon_canonical_id,
                   lookup_decision_level, minted, nexus_namespace,
                   type_hint, specificity, maturity_tier
            FROM entity
        """)
        for row in syn_cur.fetchall():
            iri = self._entity_iri(row)
            if iri is None:
                continue
            bfo = self._bfo_for_entity(row)
            lines.append(f"{iri} rdf:type {bfo} .")
            label = escape_ntriple(row["preferred_canonical"] or row["ent_id"])
            lines.append(f'{iri} rdfs:label "{label}" .')
            cid = row["lexicon_canonical_id"] or row["ent_id"]
            lines.append(f'{iri} syn:canonicalId "{cid}" .')
            ns = row["nexus_namespace"] or "synapedia"
            lines.append(f'{iri} syn:nexusNamespace "{ns}" .')
            # IS-A parents (walk from lexicon_canonical_id)
            if row["lexicon_canonical_id"]:
                parents = self._walk_isa(row["lexicon_canonical_id"])
                for p_iri, p_cid in parents:
                    lines.append(f"{iri} rdfs:subClassOf {p_iri} .")
                    parent_cids.add((p_cid, p_iri))

        # 1b. Parent nodes (from main lexicon) – declare rdf:type, rdfs:label, syn:canonicalId
        lex_conn = sqlite3.connect(self.lex_db_path)
        lex_conn.row_factory = sqlite3.Row
        for cid, iri in parent_cids:
            # Check if already declared by an entity (unlikely, but avoid duplicates)
            # We just emit declaration; duplicates in Turtle are harmless
            lex_cur = lex_conn.cursor()
            lex_cur.execute("""
                SELECT lemma, pos_ud, definition_tier, microgloss
                FROM synapedia_entry WHERE canonical_id = ?
            """, (cid,))
            entry = lex_cur.fetchone()
            if entry:
                bfo = bfo_category_to_iri(self._bfo_from_pos(entry["pos_ud"]))
                lines.append(f"{iri} rdf:type {bfo} .")
                lemma = escape_ntriple(entry["lemma"] or "")
                lines.append(f'{iri} rdfs:label "{lemma}" .')
                lines.append(f'{iri} syn:canonicalId "{cid}" .')
                lines.append(f'{iri} syn:nexusNamespace "synapedia_core" .')
            else:
                # Fallback: declare as owl:Thing with label from CID
                label = cid.split(".")[1] if "." in cid else cid
                lines.append(f"{iri} rdf:type owl:Thing .")
                lines.append(f'{iri} rdfs:label "{escape_ntriple(label)}" .')
                lines.append(f'{iri} syn:canonicalId "{cid}" .')
        lex_conn.close()

        # 1c. Synapses (events)
        syn_cur.execute("""
            SELECT synapse_id, verb_lemma, verb_canonical_id,
                   plane, epistemic_status, pov, trust_level,
                   source_span, frame_json
            FROM synapedia_synapse
        """)
        for row in syn_cur.fetchall():
            iri = self._synapse_iri(row["synapse_id"])
            lines.append(f"{iri} rdf:type syn:Event .")
            lines.append(f'{iri} rdf:type bfo:BFO_0000015 .')  # process
            if row["verb_lemma"]:
                lines.append(f'{iri} syn:verbLemma "{escape_ntriple(row["verb_lemma"])}" .')
            if row["verb_canonical_id"]:
                lines.append(f'{iri} syn:verbCanonical "{row["verb_canonical_id"]}" .')
            if row["plane"]:
                lines.append(f'{iri} syn:plane "{row["plane"]}" .')
            if row["epistemic_status"]:
                lines.append(f'{iri} syn:epistemicStatus "{row["epistemic_status"]}" .')
            if row["pov"]:
                lines.append(f'{iri} syn:pov "{row["pov"]}" .')
            if row["trust_level"]:
                lines.append(f'{iri} syn:trustLevel "{row["trust_level"]}" .')
            if row["source_span"]:
                lines.append(f'{iri} syn:sourceSpan "{escape_ntriple(row["source_span"])}" .')
            if row["frame_json"]:
                frame = json.loads(row["frame_json"])
                for k, v in frame.items():
                    if v is not None:
                        lines.append(f'{iri} syn:{k} "{escape_ntriple(str(v))}" .')

        # 1d. Groups
        syn_cur.execute("SELECT group_id, group_label, group_type FROM synapedia_group")
        for row in syn_cur.fetchall():
            iri = f"syn:Group_{row['group_id']}"
            lines.append(f"{iri} rdf:type syn:Group .")
            if row["group_label"]:
                lines.append(f'{iri} rdfs:label "{escape_ntriple(row["group_label"])}" .')
            if row["group_type"]:
                lines.append(f'{iri} syn:groupType "{row["group_type"]}" .')

        # 1e. Literals (collect distinct from spoke)
        syn_cur.execute("""
            SELECT DISTINCT literal_value
            FROM synapedia_spoke
            WHERE target_type = 'TYPED_LITERAL' AND literal_value IS NOT NULL
        """)
        for row in syn_cur.fetchall():
            val = str(row["literal_value"])
            iri = f"syn:Literal_{val.replace(' ', '_')}"
            lines.append(f"{iri} rdf:type syn:Literal .")
            lines.append(f'{iri} rdf:value "{escape_ntriple(val)}" .')

        # 1f. Ghosts (optional)
        if self.include_ghosts:
            syn_cur.execute("""
                SELECT ghost_id, label, surface_form, ttl_expiry
                FROM synapedia_ghost
                WHERE epistemic_status = 'GHOST'
            """)
            for row in syn_cur.fetchall():
                iri = f"syn:Ghost_{row['ghost_id']}"
                lines.append(f"{iri} rdf:type syn:Ghost .")
                lbl = escape_ntriple(row["label"] or row["surface_form"] or "")
                lines.append(f'{iri} rdfs:label "{lbl}" .')
                if row["ttl_expiry"]:
                    lines.append(f'{iri} syn:ttlExpiry "{row["ttl_expiry"]}"^^xsd:dateTime .')

        syn_conn.close()
        return lines

    # -----------------------------------------------------------------------
    # Pass 2: ABox / Edges
    # -----------------------------------------------------------------------

    def export_pass2(self):
        lines = []
        syn_conn = sqlite3.connect(self.syn_db_path)
        syn_conn.row_factory = sqlite3.Row
        syn_cur = syn_conn.cursor()
        lex_conn = sqlite3.connect(self.lex_db_path)
        lex_conn.row_factory = sqlite3.Row

        # 2a. Binary core relations (from main lexicon) – IS_A, HAS_PART, etc.
        # These are stored in synapedia_relation in the main lexicon DB
        lex_cur = lex_conn.cursor()
        lex_cur.execute("""
            SELECT concept_id, relation_type, target_id
            FROM synapedia_relation
        """)
        for row in lex_cur.fetchall():
            subj = canonical_id_to_iri(row["concept_id"])
            obj = canonical_id_to_iri(row["target_id"])
            if not subj or not obj:
                continue
            rt = row["relation_type"]
            if rt == "IS_A":
                lines.append(f"{subj} rdfs:subClassOf {obj} .")
            elif rt == "HAS_PART":
                lines.append(f"{subj} syn:hasPart {obj} .")
            elif rt == "HAS_MEMBER":
                lines.append(f"{subj} syn:hasMember {obj} .")
            elif rt == "HAS_INSTANCE":
                lines.append(f"{subj} syn:hasInstance {obj} .")
            elif rt == "ANTONYM_OF":
                lines.append(f"{subj} syn:antonymOf {obj} .")
            elif rt == "HAS_POSSESSOR":
                lines.append(f"{subj} syn:hasPossessor {obj} .")
            # Ignore other relations (they are not binary core)
        lex_conn.close()

        # 2b. BFO dependence relations (from main lexicon)
        lex_cur2 = lex_conn.cursor()  # re-opened
        lex_cur2.execute("""
            SELECT dependent_id, relation_type, independent_id
            FROM synapedia_dependence
        """)
        for row in lex_cur2.fetchall():
            dep = canonical_id_to_iri(row["dependent_id"])
            ind = canonical_id_to_iri(row["independent_id"])
            if not dep or not ind:
                continue
            pred = DEPENDENCE_PREDICATE.get(row["relation_type"])
            if pred:
                lines.append(f"{dep} {pred} {ind} .")
        lex_conn.close()

        # 2c. Spokes (event participation)
        syn_cur.execute("""
            SELECT sp.synapse_id, sp.role, sp.target_id, sp.target_type,
                   sp.target_lemma, sp.literal_value, sp.target_canonical_id
            FROM synapedia_spoke sp
        """)
        for row in syn_cur.fetchall():
            syn_iri = self._synapse_iri(row["synapse_id"])
            pred = ROLE_PREDICATE.get(row["role"])
            if not pred:
                # Unknown role – use syn:{role} as predicate
                pred = f"syn:{row['role']}"
            if row["target_type"] == "synapse":
                obj = self._synapse_iri(row["target_id"])
            elif row["target_type"] == "TYPED_LITERAL" and row["literal_value"]:
                val = str(row["literal_value"])
                obj = f"syn:Literal_{val.replace(' ', '_')}"
            else:
                obj = self._entity_iri_by_id(row["target_id"], row["target_canonical_id"])
                if not obj:
                    continue
            lines.append(f"{syn_iri} {pred} {obj} .")

        # 2d. Entry-to-synapse links (synapedia_entry_synapse)
        # This table is in the synapse store
        syn_cur.execute("""
            SELECT entry_id, synapse_id, relation
            FROM synapedia_entry_synapse
        """)
        for row in syn_cur.fetchall():
            entry_iri = self._entry_iri_from_id(row["entry_id"])
            syn_iri = self._synapse_iri(row["synapse_id"])
            if entry_iri and syn_iri:
                lines.append(f"{entry_iri} syn:hasEvent {syn_iri} .")

        # 2e. Group membership
        syn_cur.execute("""
            SELECT gm.group_id, gm.member_id
            FROM synapedia_group_member gm
        """)
        for row in syn_cur.fetchall():
            group_iri = f"syn:Group_{row['group_id']}"
            member_iri = self._synapse_iri(row["member_id"])
            lines.append(f"{member_iri} syn:memberOf {group_iri} .")

        # 2f. Links (PRECEDES, CAUSES, etc.)
        syn_cur.execute("""
            SELECT source_id, link_type, target_id, confidence
            FROM synapedia_link
        """)
        for row in syn_cur.fetchall():
            pred = LINK_PREDICATE.get(row["link_type"])
            if not pred:
                pred = f"syn:{row['link_type']}"
            src = self._synapse_iri(row["source_id"])
            tgt = self._synapse_iri(row["target_id"])
            if row["confidence"] is not None and row["confidence"] < 1.0:
                lines.append(f"{src} {pred} {tgt} [ syn:confidence \"{row['confidence']}\"^^xsd:float ] .")
            else:
                lines.append(f"{src} {pred} {tgt} .")

        # 2g. HAS_ATTRIBUTE from synapedia_has_attribute (main lexicon)
        # This table may exist in the main lexicon. We'll query from lex_db if exists.
        lex_conn2 = sqlite3.connect(self.lex_db_path)
        lex_cur3 = lex_conn2.cursor()
        lex_cur3.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='synapedia_has_attribute'")
        if lex_cur3.fetchone():
            lex_cur4 = lex_conn2.cursor()
            lex_cur4.execute("""
                SELECT entry_id, attribute_key, attribute_value
                FROM synapedia_has_attribute
            """)
            # entry_id references synapedia_entry. We need to map to IRI.
            # We'll join to synapedia_entry to get canonical_id.
            # Since this is rare, we do a simple approach: for each row, get a cursor
            for attr_row in lex_cur4.fetchall():
                # get canonical_id for entry_id
                cur_e = lex_conn2.cursor()
                cur_e.execute("SELECT canonical_id FROM synapedia_entry WHERE entry_id = ?", (attr_row[0],))
                row_e = cur_e.fetchone()
                if row_e and row_e[0]:
                    ent_iri = canonical_id_to_iri(row_e[0])
                    key = attr_row[1]
                    val = attr_row[2]
                    # Use reified form: entity syn:hasAttribute [ syn:key "key" ; syn:value "val" ] .
                    blank = f"_[syn_key_{key}]"
                    lines.append(f"{ent_iri} syn:hasAttribute {blank} .")
                    lines.append(f"{blank} syn:key \"{escape_ntriple(key)}\" .")
                    lines.append(f"{blank} syn:value \"{escape_ntriple(val)}\" .")
        lex_conn2.close()

        # 2h. Aliases from synapedia_alias (main lexicon)
        lex_conn3 = sqlite3.connect(self.lex_db_path)
        lex_cur5 = lex_conn3.cursor()
        lex_cur5.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='synapedia_alias'")
        if lex_cur5.fetchone():
            lex_cur6 = lex_conn3.cursor()
            lex_cur6.execute("""
                SELECT a.canonical_id, a.alias
                FROM synapedia_alias a
            """)
            for alias_row in lex_cur6.fetchall():
                ent_iri = canonical_id_to_iri(alias_row[0])
                alias_val = alias_row[1]
                if ent_iri and alias_val:
                    lines.append(f'{ent_iri} syn:alias "{escape_ntriple(alias_val)}" .')
        lex_conn3.close()

        syn_conn.close()
        return lines

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _entity_iri(self, row):
        cid = row.get("lexicon_canonical_id")
        if cid:
            return canonical_id_to_iri(cid)
        eid = row.get("ent_id")
        if eid:
            return canonical_id_to_iri(eid)
        return None

    def _entity_iri_by_id(self, target_id, target_canonical_id=None):
        if target_canonical_id:
            return canonical_id_to_iri(target_canonical_id)
        if target_id:
            return canonical_id_to_iri(target_id)
        return None

    def _entry_iri_from_id(self, entry_id):
        """Translate an integer entry_id (from synapse_store's entry table or synapedia_entry_synapse)
           to an IRI. We assume entry_id references the entity table in the synapse store."""
        conn = sqlite3.connect(self.syn_db_path)
        cur = conn.cursor()
        cur.execute("SELECT lexicon_canonical_id, ent_id FROM entity WHERE rowid = ? OR ent_id = ?",
                    (entry_id, str(entry_id)))
        row = cur.fetchone()
        conn.close()
        if row:
            cid = row[0]
            eid = row[1]
            if cid:
                return canonical_id_to_iri(cid)
            if eid:
                return canonical_id_to_iri(eid)
        return None

    def _synapse_iri(self, synapse_id):
        return f"syn:Synapse_{synapse_id}"

    def _bfo_for_entity(self, row):
        hint = (row.get("type_hint") or "").lower()
        if hint in ("person", "org", "gpe", "loc"):
            return "bfo:BFO_0000040"  # material entity
        if hint in ("work", "event", "product"):
            return "bfo:BFO_0000015"  # process
        # Check if minted and namespace custom – heuristically an instance of some class
        if row.get("minted") and row.get("nexus_namespace") in ("custom", "metonymy"):
            return "owl:Thing"
        return "owl:Thing"

    def _bfo_from_pos(self, pos_ud):
        # simplistic mapping for parent nodes
        if pos_ud in ("NOUN", "PROPN"):
            return "material_entity"
        if pos_ud == "VERB":
            return "process"
        return "material_entity"

    def _walk_isa(self, canonical_id, depth=0):
        """Walk up IS-A hierarchy in main lexicon. Returns list of (iri, cid) tuples."""
        if depth >= self.parent_depth or not canonical_id:
            return []
        conn = sqlite3.connect(self.lex_db_path)
        cur = conn.cursor()
        results = []
        cur.execute("""
            SELECT target_id FROM synapedia_relation
            WHERE concept_id = ? AND relation_type = 'IS_A'
        """, (canonical_id,))
        for row in cur.fetchall():
            parent_cid = row[0]
            parent_iri = canonical_id_to_iri(parent_cid)
            results.append((parent_iri, parent_cid))
            results.extend(self._walk_isa(parent_cid, depth + 1))
        conn.close()
        return results

    # -----------------------------------------------------------------------
    # Output generation
    # -----------------------------------------------------------------------

    def generate(self, output_format="turtle"):
        triples_pass1 = self.export_pass1()
        triples_pass2 = self.export_pass2()
        all_triples = triples_pass1 + triples_pass2
        if output_format == "sparql-insert":
            return self._format_sparql_insert(all_triples)
        else:
            return self._format_turtle(all_triples)

    def _format_turtle(self, triples):
        prefixes = "\n".join(f"@prefix {p}: <{v}> ." for p, v in NS.items())
        body = "\n".join(triples)
        return f"{prefixes}\n\n{body}\n"

    def _format_sparql_insert(self, triples):
        prefixes = "\n".join(f"PREFIX {p}: <{v}>" for p, v in NS.items())
        graph = self.graph_iri
        drop = f"DROP GRAPH {graph} ;"
        body = "\n".join(triples)
        insert = f"INSERT DATA {{ GRAPH {graph} {{ {body} }} }}"
        return f"{prefixes}\n{drop}\n{insert}\n"

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Export Synapse Store to RDF")
    parser.add_argument("--input", required=True, help="Path to synapse_store.db")
    parser.add_argument("--main-lexicon", required=True, help="Path to synapedia.db")
    parser.add_argument("--custom-db", default=None, help="Optional custom lexicon DB")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--format", default="turtle", choices=["turtle", "sparql-insert", "ntriples"])
    parser.add_argument("--parent-depth", type=int, default=1)
    parser.add_argument("--graph", default=None, help="Named graph IRI")
    parser.add_argument("--include-ghosts", action="store_true", default=False)
    args = parser.parse_args()

    if not Path(args.input).exists():
        sys.exit(f"Synapse store not found: {args.input}")
    if not Path(args.main_lexicon).exists():
        sys.exit(f"Main lexicon not found: {args.main_lexicon}")

    exporter = SparqlExporter(
        synapse_db=args.input,
        main_lexicon_db=args.main_lexicon,
        custom_db=args.custom_db,
        parent_depth=args.parent_depth,
        include_ghosts=args.include_ghosts,
        graph_iri=args.graph,
    )

    output = exporter.generate(output_format=args.format)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(output)

    line_count = len(output.splitlines())
    print(f"Exported {line_count} lines to {args.output}")
    print(f"  Format: {args.format}")
    print(f"  Parent depth: {args.parent_depth}")

if __name__ == "__main__":
    main()
