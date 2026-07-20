#!/usr/bin/env python3
"""
glean_export_cypher.py — Export the SGF Synapse Store to Cypher (Neo4j)

Two-pass export: Pass 1 creates nodes (MERGE). Pass 2 creates relationships (MERGE, not CREATE, for idempotency).
Includes referenced core lexicon entries up to configurable IS‑A parent depth.

Usage:
    python glean_export_cypher.py \\
        --input doc.synapse_store.db \\
        --main-lexicon synapedia.db \\
        --parent-depth 1 \\
        --output doc.cypher
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def escape_cypher(s):
    if s is None:
        return "null"
    s = s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return f"'{s}'"

def cid_to_cypher_id(cid):
    """Use the canonical ID as the node `id` property."""
    return cid

def cid_to_iri(cid):
    """Map canonical ID to an IRI string (for `iri` property)."""
    if cid is None:
        return None
    if cid.startswith("lit."):
        parts = cid.split(".")
        return f"syn:Literal_{parts[1]}_{parts[2]}"
    if cid.startswith("inst."):
        return f"syn:Instance_{cid.replace('.', '_')}"
    if cid.startswith("ghost."):
        return f"syn:Ghost_{cid.replace('.', '_')}"
    if cid.startswith("en."):
        return f"syn:{cid.replace('.', '_')}"
    return f"syn:{cid.replace('.', '_')}"

# ---------------------------------------------------------------------------
# Main exporter class
# ---------------------------------------------------------------------------

class CypherExporter:
    def __init__(self, synapse_db, main_lexicon_db, custom_db=None,
                 parent_depth=1, include_ghosts=False):
        self.syn_db_path = synapse_db
        self.lex_db_path = main_lexicon_db
        self.custom_db_path = custom_db
        self.parent_depth = parent_depth
        self.include_ghosts = include_ghosts
        # Track created node ids to avoid duplicate MERGE attempts (though MERGE is idempotent)
        self.created_nodes = set()

    # -----------------------------------------------------------------------
    # Pass 1: Nodes
    # -----------------------------------------------------------------------

    def export_pass1(self):
        statements = []
        syn_conn = sqlite3.connect(self.syn_db_path)
        syn_conn.row_factory = sqlite3.Row
        syn_cur = syn_conn.cursor()

        # 1a. Entities from synapse store
        syn_cur.execute("""
            SELECT ent_id, preferred_canonical, lexicon_canonical_id,
                   lookup_decision_level, minted, nexus_namespace,
                   type_hint, specificity, maturity_tier
            FROM entity
        """)
        for row in syn_cur.fetchall():
            node_id = row["lexicon_canonical_id"] or row["ent_id"]
            if node_id in self.created_nodes:
                continue
            self.created_nodes.add(node_id)
            label = self._entity_label(row)
            props = {
                "id": node_id,
                "iri": cid_to_iri(node_id),
                "label": row["preferred_canonical"] or row["ent_id"],
                "canonicalId": row["lexicon_canonical_id"] or "",
                "namespace": row["nexus_namespace"] or "synapedia",
                "typeHint": row["type_hint"] or "",
            }
            if row["specificity"]:
                props["specificity"] = row["specificity"]
            if row["maturity_tier"]:
                props["maturityTier"] = row["maturity_tier"]
            statements.append(self._merge_node(label, props))

        # 1b. Collect all referenced canonical IDs (from entities and their IS-A parents)
        all_cids = set()
        syn_cur.execute("SELECT DISTINCT lexicon_canonical_id FROM entity WHERE lexicon_canonical_id IS NOT NULL")
        for row in syn_cur.fetchall():
            all_cids.add(row[0])
        # Walk IS-A parents for each CID
        for cid in list(all_cids):
            self._collect_parent_cids(cid, all_cids)
        # Create nodes for parent CIDs that aren't yet created
        for cid in all_cids:
            if cid in self.created_nodes:
                continue
            self.created_nodes.add(cid)
            # Try to get details from main lexicon
            lex_conn = sqlite3.connect(self.lex_db_path)
            lex_cur = lex_conn.cursor()
            lex_cur.execute("SELECT lemma, pos_ud, definition_tier FROM synapedia_entry WHERE canonical_id = ?", (cid,))
            lex_row = lex_cur.fetchone()
            lex_conn.close()
            props = {
                "id": cid,
                "iri": cid_to_iri(cid),
                "canonicalId": cid,
                "namespace": self._namespace_from_cid(cid),
            }
            if lex_row:
                props["lemma"] = lex_row[0] or ""
                props["pos"] = lex_row[1] or ""
                props["tier"] = lex_row[2] or ""
                label = "CoreConcept"
            else:
                props["lemma"] = cid.split(".")[1] if "." in cid else cid
                label = "InferredConcept"
            statements.append(self._merge_node(label, props))

        # 1c. Synapses as nodes
        syn_cur.execute("""
            SELECT synapse_id, verb_lemma, verb_canonical_id,
                   plane, epistemic_status, pov, trust_level,
                   source_span, frame_json
            FROM synapedia_synapse
        """)
        for row in syn_cur.fetchall():
            node_id = row["synapse_id"]
            if node_id in self.created_nodes:
                continue
            self.created_nodes.add(node_id)
            props = {
                "id": node_id,
                "iri": f"syn:Synapse_{node_id}",
                "verbLemma": row["verb_lemma"] or "",
                "verbCanonicalId": row["verb_canonical_id"] or "",
                "plane": row["plane"] or "",
                "epistemicStatus": row["epistemic_status"] or "",
                "pov": row["pov"] or "",
                "trustLevel": row["trust_level"] or "",
            }
            if row["source_span"]:
                span = json.loads(row["source_span"])
                props["sourceSpan"] = json.dumps(span)
            if row["frame_json"]:
                props["frameJson"] = row["frame_json"]
            statements.append(self._merge_node("Synapse", props))

        # 1d. Groups
        syn_cur.execute("SELECT group_id, group_label, group_type FROM synapedia_group")
        for row in syn_cur.fetchall():
            node_id = f"Group_{row['group_id']}"
            if node_id in self.created_nodes:
                continue
            self.created_nodes.add(node_id)
            props = {
                "id": node_id,
                "label": row["group_label"] or "",
                "groupType": row["group_type"] or "",
            }
            statements.append(self._merge_node("Group", props))

        # 1e. Literals
        syn_cur.execute("""
            SELECT DISTINCT literal_value
            FROM synapedia_spoke
            WHERE target_type = 'TYPED_LITERAL' AND literal_value IS NOT NULL
        """)
        for row in syn_cur.fetchall():
            val = str(row["literal_value"])
            node_id = f"Literal_{val.replace(' ', '_')}"
            if node_id in self.created_nodes:
                continue
            self.created_nodes.add(node_id)
            props = {"id": node_id, "value": val}
            statements.append(self._merge_node("Literal", props))

        # 1f. Ghosts (optional)
        if self.include_ghosts:
            syn_cur.execute("""
                SELECT ghost_id, label, surface_form, ttl_expiry
                FROM synapedia_ghost
                WHERE epistemic_status = 'GHOST'
            """)
            for row in syn_cur.fetchall():
                node_id = f"Ghost_{row['ghost_id']}"
                if node_id in self.created_nodes:
                    continue
                self.created_nodes.add(node_id)
                props = {
                    "id": node_id,
                    "label": row["label"] or row["surface_form"] or "",
                    "ttlExpiry": row["ttl_expiry"] or "",
                }
                statements.append(self._merge_node("Ghost", props))

        syn_conn.close()
        return statements

    # -----------------------------------------------------------------------
    # Pass 2: Relationships
    # -----------------------------------------------------------------------

    def export_pass2(self):
        statements = []
        syn_conn = sqlite3.connect(self.syn_db_path)
        syn_conn.row_factory = sqlite3.Row
        syn_cur = syn_conn.cursor()
        lex_conn = sqlite3.connect(self.lex_db_path)
        lex_conn.row_factory = sqlite3.Row

        # 2a. Binary core relations (from main lexicon)
        lex_cur = lex_conn.cursor()
        lex_cur.execute("""
            SELECT concept_id, relation_type, target_id
            FROM synapedia_relation
        """)
        for row in lex_cur.fetchall():
            source_id = row["concept_id"]
            target_id = row["target_id"]
            rel_type = self._binary_core_rel_type(row["relation_type"])
            if not rel_type:
                continue
            statements.append(self._merge_rel(source_id, rel_type, target_id))

        # 2b. BFO dependence relations (from main lexicon)
        lex_cur.execute("""
            SELECT dependent_id, relation_type, independent_id
            FROM synapedia_dependence
        """)
        for row in lex_cur.fetchall():
            rel_type = row["relation_type"].upper()  # e.g., INHERES_IN
            statements.append(self._merge_rel(row["dependent_id"], rel_type, row["independent_id"]))

        lex_conn.close()

        # 2c. Spokes (event participation)
        syn_cur.execute("""
            SELECT sp.synapse_id, sp.role, sp.target_id, sp.target_type,
                   sp.target_lemma, sp.literal_value, sp.target_canonical_id
            FROM synapedia_spoke sp
        """)
        for row in syn_cur.fetchall():
            source_id = row["synapse_id"]
            rel_type = self._spoke_rel_type(row["role"])
            if not rel_type:
                continue
            if row["target_type"] == "synapse":
                target_id = row["target_id"]
            elif row["target_type"] == "TYPED_LITERAL" and row["literal_value"]:
                val = str(row["literal_value"])
                target_id = f"Literal_{val.replace(' ', '_')}"
            else:
                target_id = row["target_canonical_id"] or row["target_id"]
            if not target_id:
                continue
            statements.append(self._merge_rel(source_id, rel_type, target_id))

        # 2d. Entry-to-synapse links
        syn_cur.execute("SELECT entry_id, synapse_id FROM synapedia_entry_synapse")
        for row in syn_cur.fetchall():
            entry_id = row["entry_id"]
            synapse_id = row["synapse_id"]
            # Translate entry_id to canonical_id via entity table
            cur2 = syn_conn.cursor()
            cur2.execute("SELECT lexicon_canonical_id, ent_id FROM entity WHERE rowid = ? OR ent_id = ?",
                         (entry_id, str(entry_id)))
            ent_row = cur2.fetchone()
            if ent_row:
                source_id = ent_row[0] or ent_row[1]
                if source_id:
                    statements.append(self._merge_rel(source_id, "HAS_EVENT", synapse_id))

        # 2e. Group membership
        syn_cur.execute("SELECT gm.group_id, gm.member_id FROM synapedia_group_member gm")
        for row in syn_cur.fetchall():
            group_id = f"Group_{row['group_id']}"
            member_id = row["member_id"]
            statements.append(self._merge_rel(member_id, "MEMBER_OF", group_id))

        # 2f. Links
        syn_cur.execute("SELECT source_id, link_type, target_id, confidence FROM synapedia_link")
        for row in syn_cur.fetchall():
            rel_type = row["link_type"]
            # For links, we support a confidence property on the relationship
            # We'll use a workaround: create the relationship with a property via WITH
            # But Cypher's MERGE doesn't allow properties on pattern; we use CREATE then SET
            # Simpler: just create relationship; confidence is ignored for now.
            # If confidence is needed, we would need CREATE with SET.
            statements.append(self._merge_rel(row["source_id"], rel_type, row["target_id"]))

        # 2g. HAS_ATTRIBUTE from main lexicon's synapedia_has_attribute
        lex_conn2 = sqlite3.connect(self.lex_db_path)
        lex_cur2 = lex_conn2.cursor()
        lex_cur2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='synapedia_has_attribute'")
        if lex_cur2.fetchone():
            lex_cur3 = lex_conn2.cursor()
            lex_cur3.execute("""
                SELECT ha.entry_id, ha.attribute_key, ha.attribute_value
                FROM synapedia_has_attribute ha
            """)
            for attr_row in lex_cur3.fetchall():
                # get canonical_id for entry
                cur_e = lex_conn2.cursor()
                cur_e.execute("SELECT canonical_id FROM synapedia_entry WHERE entry_id = ?", (attr_row[0],))
                cid_row = cur_e.fetchone()
                if cid_row and cid_row[0]:
                    source_id = cid_row[0]
                    # Represent as property on node via SET (not as relationship)
                    # For simplicity, we add a property set statement.
                    key = attr_row[1]
                    val = attr_row[2]
                    # Use SET n.`hasAttribute_{key}` = 'val'
                    # But this pollutes node properties. Better: create a HAS_ATTRIBUTE relationship with key and value as properties
                    # We'll use a dedicated pattern
                    # MATCH (n {id: '...'})
                    # MERGE (n)-[:HAS_ATTRIBUTE {key: 'color', value: 'red'}]->(:AttributeValue {value: 'red'})
                    # Simpler: just add a property to the node.
                    statements.append(
                        f"MATCH (n {{id: {escape_cypher(source_id)}}})\n"
                        f"SET n.`attr_{key}` = {escape_cypher(val)};"
                    )
        lex_conn2.close()

        # 2h. Aliases from main lexicon's synapedia_alias
        lex_conn3 = sqlite3.connect(self.lex_db_path)
        lex_cur4 = lex_conn3.cursor()
        lex_cur4.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='synapedia_alias'")
        if lex_cur4.fetchone():
            lex_cur5 = lex_conn3.cursor()
            lex_cur5.execute("SELECT canonical_id, alias FROM synapedia_alias")
            for alias_row in lex_cur5.fetchall():
                source_id = alias_row[0]
                alias_val = alias_row[1]
                statements.append(
                    f"MATCH (n {{id: {escape_cypher(source_id)}}})\n"
                    f"SET n.alias = {escape_cypher(alias_val)};"
                )
        lex_conn3.close()

        syn_conn.close()
        return statements

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _entity_label(self, row):
        ns = row["nexus_namespace"] or "synapedia"
        if ns == "literal":
            return "Literal"
        if ns in ("custom", "metonymy"):
            return "Custom"
        if ns == "instance":
            return "Instance"
        if ns == "ghost":
            return "Ghost"
        return "Entity"

    def _namespace_from_cid(self, cid):
        parts = cid.split(".")
        if len(parts) >= 4:
            return parts[-1]
        return "synapedia"

    def _merge_node(self, label, props):
        """MERGE node on id, SET other properties."""
        id_val = escape_cypher(props["id"])
        set_parts = []
        for key, val in props.items():
            if key == "id":
                continue
            set_parts.append(f"n.{key} = {escape_cypher(val)}")
        set_clause = "\n".join(f"  SET {s}" for s in set_parts) if set_parts else ""
        return f"MERGE (n:{label} {{id: {id_val}}})\n{set_clause}\n;"

    def _merge_rel(self, source_id, rel_type, target_id):
        """MERGE relationship pattern. This is idempotent: if the relationship already exists,
        MERGE will not create a duplicate."""
        src = escape_cypher(source_id)
        tgt = escape_cypher(target_id)
        return f"MATCH (a {{id: {src}}}), (b {{id: {tgt}}})\nMERGE (a)-[:{rel_type}]->(b);"

    def _binary_core_rel_type(self, rt):
        mapping = {
            "IS_A": "IS_A",
            "HAS_PART": "HAS_PART",
            "HAS_MEMBER": "HAS_MEMBER",
            "HAS_INSTANCE": "HAS_INSTANCE",
            "ANTONYM_OF": "ANTONYM_OF",
            "HAS_POSSESSOR": "HAS_POSSESSOR",
        }
        return mapping.get(rt)

    def _spoke_rel_type(self, role):
        mapping = {
            "HAS_AGENT": "HAS_AGENT",
            "HAS_PATIENT": "HAS_PATIENT",
            "HAS_THEME": "HAS_THEME",
            "HAS_EXPERIENCER": "HAS_EXPERIENCER",
            "HAS_RECIPIENT": "HAS_RECIPIENT",
            "HAS_BENEFICIARY": "HAS_BENEFICIARY",
            "HAS_TIME": "HAS_TIME",
            "HAS_LOCATION": "HAS_LOCATION",
            "HAS_SOURCE": "HAS_SOURCE",
            "HAS_DESTINATION": "HAS_DESTINATION",
            "HAS_MANNER": "HAS_MANNER",
            "HAS_INSTRUMENT": "HAS_INSTRUMENT",
            "HAS_CAUSE": "HAS_CAUSE",
            "HAS_REASON": "HAS_REASON",
            "HAS_ATTRIBUTE": "HAS_ATTRIBUTE",
        }
        return mapping.get(role)

    def _collect_parent_cids(self, cid, cid_set, depth=0):
        if depth >= self.parent_depth or not cid:
            return
        conn = sqlite3.connect(self.lex_db_path)
        cur = conn.cursor()
        cur.execute("SELECT target_id FROM synapedia_relation WHERE concept_id = ? AND relation_type = 'IS_A'", (cid,))
        for row in cur.fetchall():
            p_cid = row[0]
            if p_cid not in cid_set:
                cid_set.add(p_cid)
                self._collect_parent_cids(p_cid, cid_set, depth + 1)
        conn.close()

    # -----------------------------------------------------------------------
    # Output generation
    # -----------------------------------------------------------------------

    def generate(self):
        stmts1 = self.export_pass1()
        stmts2 = self.export_pass2()
        result = "// Generated by glean_export_cypher.py\n"
        result += ":BEGIN\n"
        result += "\n".join(stmts1) + "\n"
        result += "\n".join(stmts2) + "\n"
        result += ":COMMIT\n"
        return result

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Export Synapse Store to Cypher")
    parser.add_argument("--input", required=True, help="Path to synapse_store.db")
    parser.add_argument("--main-lexicon", required=True, help="Path to synapedia.db")
    parser.add_argument("--custom-db", default=None, help="Optional custom lexicon DB")
    parser.add_argument("--output", required=True, help="Output .cypher file")
    parser.add_argument("--parent-depth", type=int, default=1)
    parser.add_argument("--include-ghosts", action="store_true", default=False)
    args = parser.parse_args()

    if not Path(args.input).exists():
        sys.exit(f"Synapse store not found: {args.input}")
    if not Path(args.main_lexicon).exists():
        sys.exit(f"Main lexicon not found: {args.main_lexicon}")

    exporter = CypherExporter(
        synapse_db=args.input,
        main_lexicon_db=args.main_lexicon,
        custom_db=args.custom_db,
        parent_depth=args.parent_depth,
        include_ghosts=args.include_ghosts,
    )
    output = exporter.generate()
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(output)
    stmt_count = output.count("MERGE") + output.count("MATCH")
    print(f"Exported to {args.output}")

if __name__ == "__main__":
    main()
