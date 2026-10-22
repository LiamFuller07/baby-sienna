"""Synthetic regressions from running real sources through the toolkit."""
import argparse
from email.message import EmailMessage
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bs
bs.load()

spec = importlib.util.spec_from_file_location('map_builder', ROOT/'design-system/process-map/build_map.py')
maps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maps)


class EvidenceRun(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name)/'workspace'
        shutil.copytree(ROOT/'examples', self.ws, ignore=shutil.ignore_patterns('out'))

    def map(self):
        return json.loads((self.ws/'process-map/current-state.json').read_text())

    def save_map(self, data):
        (self.ws/'process-map/current-state.json').write_text(json.dumps(data))

    def convert(self, path, sid, partial=True):
        args = argparse.Namespace(id=sid, kind='document', title='Source document', captured='2026-10-22',
                                  detail=None, url=None, legacy=False, partial=partial)
        with redirect_stdout(io.StringIO()):
            bs.convert(self.ws, path, args)

    def test_email_body_and_attachment_boundary(self):
        msg = EmailMessage()
        msg['From'] = 'team-a@example.test'
        msg['Subject'] = 'Source files'
        body = 'Received text. ' * 700
        msg.set_content(body)
        msg.add_attachment(b'private attachment bytes', maintype='application', subtype='octet-stream', filename='attachment.bin')
        p = self.ws/'inputs/message.eml'
        p.write_bytes(msg.as_bytes())
        units = bs.read_eml(p)
        combined = ''.join(t for _, t, _ in units)
        self.assertIn(body, combined)
        self.assertNotIn('private attachment bytes', combined)
        self.assertTrue(all(len(t) <= 4000 for _, t, _ in units))
        with self.assertRaisesRegex(SystemExit, '--partial'):
            self.convert('inputs/message.eml', 'EMAIL', False)
        self.convert('inputs/message.eml', 'EMAIL')
        self.assertFalse(bs.check(self.ws).errors())

    def test_pdf_originals_are_reread(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest('optional PDF reader not installed')
        p = self.ws/'inputs/process.pdf'
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((50, 50), 'Team A receives the request.')
            page.insert_text((50, 100), 'Team B reviews the request.')
            doc.new_page()  # image-only or blank page must not imply complete semantics
            doc.save(p)
        with self.assertRaisesRegex(SystemExit, '--partial'):
            self.convert('inputs/process.pdf', 'PDF', False)
        self.convert('inputs/process.pdf', 'PDF')
        self.assertFalse(bs.check(self.ws).errors())
        rec = self.ws/'records/PDF.json'
        data = json.loads(rec.read_text())
        data['records'][0]['text'] = 'Invented approval.'
        rec.write_text(json.dumps(data))
        self.assertIn('rec-5', bs.check(self.ws).rules())
        p.write_bytes(p.read_bytes()+b'changed')
        self.assertIn('rec-2', bs.check(self.ws).rules())

    def test_native_visio_cannot_masquerade_as_pdf(self):
        p = self.ws/'inputs/diagram.vsdx'
        p.write_bytes(b'PK\x03\x04native visio')
        with self.assertRaisesRegex(bs.ReadError, 'not PDF bytes'):
            bs.read_pdf(p)

    def test_connection_quote_is_checked(self):
        data = self.map()
        data['edges'][0]['cite'] = [{'source':'T1', 'locator':'00:00:05', 'quote':'Invented connection'}]
        self.save_map(data)
        self.assertIn('cite-2', bs.check(self.ws).rules())

    def test_distinct_branches_can_converge(self):
        data = self.map()
        branches = [e for e in data['edges'] if e.get('kind')=='conditional']
        branches[1]['to'] = branches[0]['to']
        self.save_map(data)
        self.assertNotIn('map-5', bs.check(self.ws).rules())
        data['edges'].append(dict(branches[0]))
        self.save_map(data)
        self.assertIn('map-5', bs.check(self.ws).rules())

    def test_incomplete_branch_requires_visible_clarification(self):
        data = self.map()
        decision = next(n for n in data['nodes'] if n.get('kind')=='decision')
        data['edges'] = [e for e in data['edges'] if e.get('label')!='No']
        decision['branchesIncomplete'] = True
        self.save_map(data)
        self.assertIn('map-4', bs.check(self.ws).rules())
        data['clarifications'][0]['nodes'].append(decision['id'])
        self.save_map(data)
        self.assertNotIn('map-4', bs.check(self.ws).rules())

    def test_map_level_annotation_is_not_a_fake_step(self):
        data = self.map()
        data['clarifications'][0]['nodes'] = []
        self.save_map(data)
        self.assertFalse(bs.check(self.ws).errors())

    def test_router_preserves_edges_avoids_cards_and_fits_labels(self):
        data = self.map()
        # Two labelled branches converge on the same destination across lanes.
        branches = [e for e in data['edges'] if e.get('kind')=='conditional']
        branches[1]['to'] = branches[0]['to']
        branches[0]['label'] = 'Complete'
        branches[1]['label'] = 'Incomplete'
        idx = maps.Index(self.ws, json.loads((ROOT/"formats/citation-types.json").read_text()))
        model = maps.MapModel(data, idx, 'synthetic')
        self.assertEqual(len(model.routes), len(data['edges']))
        for route in model.routes:
            self.assertTrue(model.clear_route(route['pts']))
            self.assertTrue(all(a[0]==b[0] or a[1]==b[1] for a,b in zip(route['pts'],route['pts'][1:])))
            if route['e'].get('kind')=='conditional':
                self.assertIsNotNone(route['pill'])
        other = maps.MapModel(data, idx, 'synthetic')
        self.assertEqual([r['pts'] for r in model.routes], [r['pts'] for r in other.routes])


if __name__ == '__main__':
    unittest.main()
