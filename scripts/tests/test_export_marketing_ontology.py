"""Regression checks for the offline OWL exporter; never opens the application DB."""
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rdflib import Graph, Literal, RDF, RDFS, OWL, XSD
from rdflib.collection import Collection
from rdflib.compare import isomorphic

spec = importlib.util.spec_from_file_location("owl_export", Path(__file__).resolve().parents[1] / "export_marketing_ontology.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


def entity(row_id, tenant, external_id, kind="Product", attrs=None):
    return {"id": row_id, "tenant_id": tenant, "external_id": external_id, "entity_type": kind,
            "label": "样例产品", "attributes_json": json.dumps(attrs or {}, ensure_ascii=False),
            "source": "fixture", "confidence": 0.95, "import_job_id": None, "updated_at": "2026-09-22 09:00:00"}


def edge(row_id, source, target, kind="contains_product", tenant=1):
    return {"id": row_id, "tenant_id": tenant, "source_entity_id": source, "target_entity_id": target,
            "relation_type": kind, "evidence": "测试证据", "source": "fixture", "confidence": 0.9,
            "import_job_id": None, "created_at": "2026-09-22 09:00:00"}


def snapshot(entities=None, relations=None):
    return {"tenants": [{"id": 1, "name": "东航"}, {"id": 2, "name": "第二租户"}],
            "entities": entities or [], "relations": relations or [], "business_counts": {}}


class OwlExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = e.load_model()

    def test_complete_registry_and_json_contracts_roundtrip(self):
        g, summary = e.build_graph(self.model, snapshot())
        self.assertEqual(len(list(g.subjects(RDF.type, OWL.NamedIndividual))), 0)
        self.assertEqual(summary["registered_class_count"], 41)
        self.assertEqual(summary["owl_named_class_count"], 41)
        self.assertEqual(summary["owl_object_property_count"], 44)
        restored = json.loads(str(g.value(e.ONT, e.M.registryJson)))
        self.assertEqual(restored, self.model)
        self.assertEqual(len(list(g.objects(e.ONT, e.M.actionDefinition))), 14)
        self.assertEqual(len(list(g.objects(e.ONT, e.M.functionDefinition))), 13)
        self.assertEqual(len(list(g.objects(e.ONT, e.M.agentContract))), 6)
        parsed = Graph().parse(data=g.serialize(format="xml"), format="xml")
        self.assertTrue(isomorphic(g, parsed))

    def test_relation_types_use_union_not_multiple_domains(self):
        definition = next(x for x in self.model["relation_types"] if len(x["from_types"]) > 1)
        g, _ = e.build_graph(self.model, snapshot())
        prop = e.P[e.identifier(definition["id"])]
        domains = list(g.objects(prop, RDFS.domain))
        self.assertEqual(len(domains), 1)
        head = g.value(domains[0], OWL.unionOf)
        self.assertEqual(set(Collection(g, head)), {e.class_uri(x) for x in definition["from_types"]})

    def test_tenant_ids_are_separate_and_values_preserved(self):
        attrs = {"price": 680, "active": False, "count": 0, "optional": None,
                 "nested": {"备注": "中文"}, "array": [None, 1, "名称"], "odd/字段": "可读"}
        first = entity(1, 1, "同名/01", attrs=attrs)
        second = entity(2, 2, "同名/01", attrs=attrs)
        g, summary = e.build_graph(self.model, snapshot([first, second]))
        self.assertNotEqual(e.instance_uri(first), e.instance_uri(second))
        self.assertEqual(summary["entity_count"], 2)
        raw = g.value(e.instance_uri(first), e.M.rawAttributesJson)
        self.assertEqual(json.loads(str(raw)), attrs)
        false_value = g.value(e.instance_uri(first), e.attribute_uri("Product", "active"))
        self.assertEqual(false_value.datatype, XSD.boolean)
        self.assertEqual(false_value.toPython(), False)
        self.assertEqual(g.value(e.instance_uri(first), e.attribute_uri("Product", "count")).toPython(), 0)
        self.assertIsNone(g.value(e.instance_uri(first), e.attribute_uri("Product", "optional")))
        self.assertEqual(json.loads(str(g.value(e.instance_uri(first), e.attribute_uri("Product", "nested")))), attrs["nested"])
        self.assertTrue(isomorphic(g, Graph().parse(data=g.serialize(format="xml"), format="xml")))

    def test_multiple_evidence_rows_are_not_discarded(self):
        rows = [entity(1, 1, "pack", "ProductPackage"), entity(2, 1, "prod")]
        rels = [edge(1, 1, 2), edge(2, 1, 2)]
        rels[1]["evidence"] = "另一个来源"
        g, summary = e.build_graph(self.model, snapshot(rows, rels))
        self.assertEqual(summary["relation_row_count"], 2)
        self.assertEqual(summary["distinct_relation_assertion_count"], 1)
        self.assertEqual(len(list(g.subjects(RDF.type, OWL.Axiom))), 2)
        self.assertEqual(summary["warnings"], [])

    def test_missing_and_cross_tenant_endpoints_not_asserted(self):
        rows = [entity(1, 1, "pack", "ProductPackage"), entity(2, 2, "prod")]
        rels = [edge(1, 1, 2), edge(2, 1, 99)]
        g, summary = e.build_graph(self.model, snapshot(rows, rels))
        self.assertEqual(summary["asserted_relation_row_count"], 0)
        self.assertEqual(summary["unasserted_relation_row_count"], 2)
        self.assertEqual(len(list(g.objects(e.ONT, e.M.unassertedRelationJson))), 2)

    def test_unknown_extensions_preserved_with_warning(self):
        rows = [entity(1, 1, "one", "Custom/类型"), entity(2, 1, "two")]
        g, summary = e.build_graph(self.model, snapshot(rows, [edge(1, 1, 2, "自定义/关联")]))
        self.assertEqual(summary["owl_named_class_count"], 42)
        self.assertEqual(summary["owl_object_property_count"], 45)
        self.assertEqual({w["code"] for w in summary["warnings"]}, {"unregistered_type", "unregistered_relation"})
        self.assertTrue(isomorphic(g, Graph().parse(data=g.serialize(format="xml"), format="xml")))

    def test_readonly_snapshot_does_not_create_missing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.db"
            with self.assertRaises(FileNotFoundError):
                e.read_snapshot(path)
            self.assertFalse(path.exists())
            path = Path(tmp) / "local.db"
            with closing(sqlite3.connect(path)) as conn:
                conn.executescript("CREATE TABLE tenants(id INTEGER,name TEXT); "
                                   "CREATE TABLE ontology_entities(id INTEGER,tenant_id INTEGER); "
                                   "CREATE TABLE ontology_relations(id INTEGER,tenant_id INTEGER); "
                                   "INSERT INTO tenants VALUES(1,'test');")
                conn.commit()
            before = path.read_bytes()
            result = e.read_snapshot(path)
            self.assertEqual(len(result["tenants"]), 1)
            self.assertEqual(path.read_bytes(), before)

    def test_version_metadata_and_mismatched_endpoints(self):
        rows = [entity(1, 1, "wrong-source"), entity(2, 1, "wrong-target", "Airport")]
        g, summary = e.build_graph(self.model, snapshot(rows, [edge(1, 1, 2)]), export_version="v1.2")
        self.assertEqual(str(g.value(e.ONT, OWL.versionInfo)), "v1.2")
        self.assertEqual(summary["export_version"], "v1.2")
        self.assertEqual(summary["asserted_relation_row_count"], 1)
        self.assertEqual(summary["warnings"][0]["code"], "endpoint_type_mismatch")


if __name__ == "__main__":
    unittest.main()
