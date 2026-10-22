#!/usr/bin/env python3
"""Each broken copy of example-proposal.json must fail with a clear message, and write nothing.
Also checks the schema with the standard jsonschema validator, when it is installed."""
import copy, json, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
BASE = json.loads((HERE / "example-proposal.json").read_text())


def slide(d, t):
    return next(s for s in d["slides"] if s["type"] == t)


CASES = [
    ("missing required field: cover.lead", lambda d: slide(d, "cover").pop("lead"), "slide 1 (cover) lead: required field is missing"),
    ("missing meta.client.name", lambda d: d["meta"]["client"].pop("name"), "meta.client.name: required field is missing"),
    ("uncited client claim (situation point)", lambda d: slide(d, "situation")["points"][0].pop("cite"), "uncited client claim"),
    ("uncited client claim (stat)", lambda d: slide(d, "situation")["stats"][0].pop("cite"), "uncited client claim"),
    ("uncited client claim (focus evidence)", lambda d: slide(d, "focus")["options"][0]["evidence"].pop("cite"), "uncited client claim"),
    ("empty cite list", lambda d: slide(d, "situation")["points"][1].update(cite=[]), "empty cite list"),
    ("cites an unknown source", lambda d: slide(d, "situation")["points"][1]["cite"][0].update(source="S9"), "cites S9, which is not in sources[]"),
    ("missing required slide", lambda d: d["slides"].remove(slide(d, "needs")), 'missing required slide: add a "needs" slide'),
    ("cover not first", lambda d: d["slides"].insert(0, d["slides"].pop(1)), "the first slide must be the cover"),
    ("sources not last", lambda d: d["slides"].insert(2, d["slides"].pop()), "the sources slide must be the last slide"),
    ("unknown slide type", lambda d: d["slides"].insert(3, {"type": "agenda", "title": "Agenda"}), '"agenda" is not allowed'),
    ("unknown field", lambda d: slide(d, "focus").update(colour="red"), "focus) colour: unknown field"),
    ("field past its layout limit", lambda d: slide(d, "focus").update(title="A title that is far too long to fit on one line of this slide"), "the slide has room for 46"),
    ("title ends with a full stop", lambda d: slide(d, "process").update(title="How it will work."), "must not end with a full stop"),
    ("bad date", lambda d: d["meta"].update(date="22/10/2026"), "must be an ISO date"),
    ("duplicate source id", lambda d: d["sources"].append(dict(d["sources"][0])), "the ID S1 is used more than once"),
    ("real logo image is not allowed", lambda d: slide(d, "team")["firms"]["logos"][0].update(image="logo.png"), "image: unknown field"),
    ("strict: client fact in a plain field", lambda d: slide(d, "process").update(lead="Client A runs 3 teams across this process."), "names Client A with a figure but is not a cited claim"),
]

failed = 0
with tempfile.TemporaryDirectory() as tmp:
    for name, mutate, expect in CASES:
        d = copy.deepcopy(BASE)
        mutate(d)
        src, out = Path(tmp) / "case.json", Path(tmp) / "case.html"
        src.write_text(json.dumps(d))
        args = [sys.executable, str(HERE / "build_proposal.py"), str(src), str(out)] + (["--strict"] if name.startswith("strict") else [])
        r = subprocess.run(args, capture_output=True, text=True)
        ok = r.returncode == 1 and expect in r.stderr and not out.exists()
        failed += not ok
        first = next((l.strip() for l in r.stderr.splitlines() if l.strip().startswith("- ")), r.stderr.strip()[:200])
        print(f"{'ok  ' if ok else 'FAIL'} {name}\n       {first}")

try:
    import jsonschema
    schema = json.loads((HERE / "proposal.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    v = jsonschema.Draft202012Validator(schema)
    for f in ("example-proposal.json", "template.json", "qa/stress.json"):
        errs = list(v.iter_errors(json.loads((HERE / f).read_text())))
        print(f"{'ok  ' if not errs else 'FAIL'} jsonschema (Draft 2020-12) accepts {f}" + (f": {errs[0].message}" if errs else ""))
        failed += bool(errs)
    bad = copy.deepcopy(BASE)
    slide(bad, "situation")["points"][0].pop("cite")
    rejected = not v.is_valid(bad)
    print(f"{'ok  ' if rejected else 'FAIL'} jsonschema also rejects an uncited claim")
    failed += not rejected
except ImportError:
    print("note: jsonschema is not installed; skipped the standard-validator check")
print(f"\n{len(CASES)} broken inputs; {'all failed clearly' if not failed else str(failed) + ' problem(s)'}")
sys.exit(1 if failed else 0)
