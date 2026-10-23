"""Synthetic regressions from running real sources through the toolkit."""

import argparse
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bs  # noqa: E402

bs.load()

spec = importlib.util.spec_from_file_location("map_builder", ROOT / "design-system/process-map/build_map.py")
maps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maps)


class EvidenceRun(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name) / "workspace"
        shutil.copytree(ROOT / "examples", self.ws, ignore=shutil.ignore_patterns("out"))

    def map(self):
        return json.loads((self.ws / "process-map/current-state.json").read_text())

    def save_map(self, data):
        (self.ws / "process-map/current-state.json").write_text(json.dumps(data))

    def convert(self, path, sid, partial=True):
        args = argparse.Namespace(
            id=sid,
            kind="document",
            title="Source document",
            captured="2026-10-22",
            detail=None,
            url=None,
            legacy=False,
            partial=partial,
        )
        with redirect_stdout(io.StringIO()):
            bs.convert(self.ws, path, args)

    def test_email_body_and_attachment_boundary(self):
        msg = EmailMessage()
        msg["From"] = "team-a@example.test"
        msg["Subject"] = "Source files"
        body = "Received text. " * 700
        msg.set_content(body)
        msg.add_attachment(
            b"private attachment bytes",
            maintype="application",
            subtype="octet-stream",
            filename="attachment.bin",
        )
        p = self.ws / "inputs/message.eml"
        p.write_bytes(msg.as_bytes())
        units = bs.read_eml(p)
        combined = "".join(t for _, t, _ in units)
        self.assertIn(body, combined)
        self.assertNotIn("private attachment bytes", combined)
        self.assertTrue(all(len(t) <= 4000 for _, t, _ in units))
        with self.assertRaisesRegex(SystemExit, "--partial"):
            self.convert("inputs/message.eml", "EMAIL", False)
        self.convert("inputs/message.eml", "EMAIL")
        self.assertFalse(bs.check(self.ws).errors())

    def test_pdf_originals_are_reread(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("optional PDF reader not installed")
        p = self.ws / "inputs/process.pdf"
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((50, 50), "Team A receives the request.")
            page.insert_text((50, 100), "Team B reviews the request.")
            doc.new_page()  # image-only or blank page must not imply complete semantics
            doc.save(p)
        with self.assertRaisesRegex(SystemExit, "--partial"):
            self.convert("inputs/process.pdf", "PDF", False)
        self.convert("inputs/process.pdf", "PDF")
        self.assertFalse(bs.check(self.ws).errors())
        rec = self.ws / "records/PDF.json"
        data = json.loads(rec.read_text())
        data["records"][0]["text"] = "Invented approval."
        rec.write_text(json.dumps(data))
        self.assertIn("rec-5", bs.check(self.ws).rules())
        p.write_bytes(p.read_bytes() + b"changed")
        self.assertIn("rec-2", bs.check(self.ws).rules())

    def test_native_visio_cannot_masquerade_as_pdf(self):
        p = self.ws / "inputs/diagram.vsdx"
        p.write_bytes(b"PK\x03\x04native visio")
        with self.assertRaisesRegex(bs.ReadError, "not PDF bytes"):
            bs.read_pdf(p)

    def test_connection_quote_is_checked(self):
        data = self.map()
        data["edges"][0]["cite"] = [{"source": "T1", "locator": "00:00:05", "quote": "Invented connection"}]
        self.save_map(data)
        self.assertIn("cite-2", bs.check(self.ws).rules())

    def test_distinct_branches_can_converge(self):
        data = self.map()
        branches = [e for e in data["edges"] if e.get("kind") == "conditional"]
        branches[1]["to"] = branches[0]["to"]
        self.save_map(data)
        self.assertNotIn("map-5", bs.check(self.ws).rules())
        data["edges"].append(dict(branches[0]))
        self.save_map(data)
        self.assertIn("map-5", bs.check(self.ws).rules())

    def test_incomplete_branch_requires_visible_clarification(self):
        data = self.map()
        decision = next(n for n in data["nodes"] if n.get("kind") == "decision")
        data["edges"] = [e for e in data["edges"] if e.get("label") != "No"]
        decision["branchesIncomplete"] = True
        self.save_map(data)
        self.assertIn("map-4", bs.check(self.ws).rules())
        data["clarifications"][0]["nodes"].append(decision["id"])
        self.save_map(data)
        self.assertNotIn("map-4", bs.check(self.ws).rules())

    def test_map_level_annotation_is_not_a_fake_step(self):
        data = self.map()
        data["clarifications"][0]["nodes"] = []
        data["clarifications"][0]["scope"] = "map"
        self.save_map(data)
        self.assertFalse(bs.check(self.ws).errors())

    def test_router_preserves_edges_avoids_cards_and_fits_labels(self):
        data = self.map()
        data["routing"] = "detour"
        next(n for n in data["nodes"] if n["id"] == "APP-01")["col"] = 5
        # Two labelled branches converge on the same destination across lanes.
        branches = [e for e in data["edges"] if e.get("kind") == "conditional"]
        branches[1]["to"] = branches[0]["to"]
        branches[0]["label"] = "Complete"
        branches[1]["label"] = "Incomplete"
        idx = maps.Index(self.ws, json.loads((ROOT / "formats/citation-types.json").read_text()))
        model = maps.MapModel(data, idx, "synthetic")
        self.assertEqual(len(model.routes), len(data["edges"]))
        for route in model.routes:
            self.assertTrue(model.clear_route(route["pts"]))
            self.assertTrue(
                all(
                    a[0] == b[0] or a[1] == b[1] for a, b in zip(route["pts"], route["pts"][1:], strict=False)
                )
            )
            if route["e"].get("kind") == "conditional":
                self.assertIsNotNone(route["pill"])
        other = maps.MapModel(data, idx, "synthetic")
        self.assertEqual([r["pts"] for r in model.routes], [r["pts"] for r in other.routes])

    def test_detour_routes_four_independent_sources_without_inventing_a_step(self):
        data = self.map()
        data["routing"] = "detour"
        data["groups"] = []
        data["gaps"] = []
        data["clarifications"] = []
        data["systems"] = []
        nodes = [n for n in data["nodes"] if n.get("kind") != "decision"][:5]
        data["lanes"] = []
        for i, node in enumerate(nodes):
            lane = f"team-{i}"
            node.update(lane=lane, state="grounded", owner=f"Team {chr(65 + i)}", systems=[])
            node.pop("group", None)
            data["lanes"].append({"id": lane, "label": f"Team {chr(65 + i)}"})
        data["nodes"] = nodes
        data["edges"] = [{"from": n["id"], "to": nodes[-1]["id"]} for n in nodes[:-1]]
        idx = maps.Index(self.ws, json.loads((ROOT / "formats/citation-types.json").read_text()))
        model = maps.MapModel(data, idx, "synthetic-fan-in")
        self.assertEqual(len(model.nodes), 5)
        self.assertEqual(len(model.routes), 4)
        self.assertFalse(model.lines_clear(model.marks()))

    def test_unstated_branch_needs_grounded_geometry_and_explicit_clarification(self):
        data = self.map()
        edge = next(e for e in data["edges"] if e.get("kind") == "conditional")
        edge.pop("label")
        edge.update(labelUnstated=True, cite=[{"source": "WB1", "locator": "Steps row 5"}])
        self.save_map(data)
        for builtin in (False, True):
            self.assertIn("map-4", bs.check(self.ws, builtin).rules())
        decision = next(n for n in data["nodes"] if n["id"] == edge["from"])
        decision["branchesIncomplete"] = True
        data["clarifications"][0]["nodes"].append(decision["id"])
        self.save_map(data)
        for builtin in (False, True):
            self.assertFalse(bs.check(self.ws, builtin).errors())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(bs.build(self.ws, "process-map/current-state", builtin), 0)
            self.assertIn(
                "Condition not stated", (self.ws / "out/process-map/current-state.html").read_text()
            )
        edge["cite"] = []
        self.save_map(data)
        self.assertIn("schema-1", bs.check(self.ws).rules())

    def test_citation_index_navigation_is_allowed_but_dangling_anchor_is_not(self):
        doc = self.ws / "document/request-handling-summary.md"
        doc.write_text(
            doc.read_text() + "\n:::aside Navigation\n[All citation points](../citation-points.html)\n:::\n"
        )
        with redirect_stdout(io.StringIO()) as log:
            self.assertEqual(bs.build(self.ws, None, False), 0, log.getvalue())
        doc_page = (self.ws / "out/document/request-handling-summary.html").read_text()
        points = bs.parse_html((self.ws / "out/citation-points.html").read_text())
        rep = bs.Report()
        bs.rule_points(
            rep,
            "out/citation-points.html",
            points,
            {
                "out/document/request-handling-summary.html": bs.parse_html(
                    doc_page.replace(
                        'href="../citation-points.html"', 'href="../citation-points.html#missing-point"'
                    )
                )
            },
        )
        self.assertIn("build-1", rep.rules())
        self.assertTrue(any("missing-point" in finding[3] for finding in rep.errors()))

    def observed_inventory(self):
        for path in (self.ws / "inventory").glob("*.json"):
            path.unlink()
        data = {
            "type": "inventory",
            "map": "end-to-end",
            "mode": "observed",
            "modules": [
                {
                    "id": "MOD-01",
                    "title": "Budget holding",
                    "software": "Software C",
                    "steps": ["RSV-01"],
                    "cite": [{"source": "D2", "locator": "¶3"}],
                }
            ],
        }
        path = self.ws / "inventory/observed.json"
        path.write_text(json.dumps(data))
        return path, data

    def test_observed_inventory_does_not_invent_suggestions(self):
        self.observed_inventory()
        for builtin in (False, True):
            with self.subTest(builtin=builtin):
                self.assertFalse(bs.check(self.ws, builtin).errors())
                with redirect_stdout(io.StringIO()) as log:
                    self.assertEqual(bs.build(self.ws, None, builtin), 0, log.getvalue())
                for name in ("data-received.html", "systems-inventory.html"):
                    page = (self.ws / "out" / name).read_text()
                    self.assertIn("Documented modules and capabilities", page)
                    self.assertIn("Observed in supplied sources", page)
                    self.assertNotIn("Modules likely to be used", page)
                    self.assertNotIn("we suggest", page)
                    self.assertNotIn("our suggestion</span>", page)
                    self.assertIn("Systems and capabilities linked to mapped steps", page)
                    self.assertIn("not a live system verification", page)
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(bs.build(self.ws, None, builtin), 0)

    def test_observed_inventory_rejects_inference_likelihood_and_unrelated_steps(self):
        path, observed = self.observed_inventory()
        variants = [
            (
                "inferred",
                "cite-4",
                lambda d: d["modules"][0].update(
                    cite=[
                        {
                            "type": "inferred",
                            "reading": "Finance holds the budget",
                            "from": [{"source": "D2", "locator": "¶3"}],
                        }
                    ]
                ),
            ),
            ("likelihood", "schema-1", lambda d: d["modules"][0].update(likelihood="likely")),
            ("unrelated step", "inv-2", lambda d: d["modules"][0].update(steps=["DUP-01"])),
            ("inferred software", "inv-2", lambda d: d["modules"][0].update(software="Software B")),
            ("default remains suggested", "schema-1", lambda d: d.pop("mode")),
        ]
        for builtin in (False, True):
            for name, rule, mutate in variants:
                with self.subTest(builtin=builtin, change=name):
                    data = json.loads(json.dumps(observed))
                    mutate(data)
                    path.write_text(json.dumps(data))
                    self.assertIn(rule, bs.check(self.ws, builtin).rules())

    def test_edge_evidence_has_markers_and_global_used_by_links(self):
        data = self.map()
        data["edges"][0]["cite"] = [
            {
                "type": "inferred",
                "reading": "The request is passed to the logging team",
                "from": [{"source": "T1", "locator": "00:00:05"}],
            }
        ]
        self.save_map(data)
        with redirect_stdout(io.StringIO()) as log:
            self.assertEqual(bs.build(self.ws, None, False), 0, log.getvalue())
        page = (self.ws / "out/process-map/current-state.html").read_text()
        root = bs.parse_html(page)
        card = next(el for el in root.walk() if el.attrs.get("id") == "connection-1")
        self.assertTrue(any("cp-mk" in el.classes() for el in card.walk()))
        self.assertIn('aria-label="Citation points"', page)
        self.assertIn('class="pm-flow is-inferred"', page)
        self.assertIn("Inferred connection", page)
        self.assertIn('href="#connection-1"', page)
        global_page = (self.ws / "out/citation-points.html").read_text()
        self.assertIn('href="process-map/current-state.html#connection-1"', global_page)
        # Dropping the connection's markers must fail exactly the same required-element check as nodes.
        card.kids = ["Connection without its marker"]
        findings = bs.unfulfilled(self.ws, bs.check(self.ws), "process-map", "current-state", root)
        self.assertTrue(any("connection-1 carries no numbered marker" in why for _, why, _ in findings))

    def test_map_scope_does_not_excuse_unknown_step_order(self):
        data = self.map()
        data["clarifications"][0].update(nodes=[], scope="map")
        data["edges"] = [e for e in data["edges"] if "REC-01" not in (e["from"], e["to"])]
        self.save_map(data)
        for builtin in (False, True):
            with redirect_stdout(io.StringIO()) as log:
                self.assertEqual(bs.build(self.ws, "process-map/current-state", builtin), 1)
            self.assertIn("build-7", log.getvalue())
            self.assertIn("Flows", log.getvalue())


if __name__ == "__main__":
    unittest.main()
