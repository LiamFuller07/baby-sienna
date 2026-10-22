#!/usr/bin/env python3
"""Worst-case deck: every string at its schema maxLength, every array at maxItems.

    python3 qa/stress.py qa/stress.json        # then build it and run qa/render.js

If this deck renders with no overflow, the schema's limits are safe layout limits.
Strings are made of ordinary English words so line breaking is realistic.
"""
import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
schema = json.loads((HERE / "proposal.schema.json").read_text())
D = schema["$defs"]
WORDS = ("the process owner reviews each step and records what changed across teams systems and weeks "
         "before approval with evidence from interviews documents spreadsheets and follow-up questions").split()
counter = itertools.count()


def text(n):
    """A sentence of real words, exactly n characters long, no final full stop."""
    out, i = "", next(counter)
    while len(out) < n:
        w = WORDS[i % len(WORDS)]
        i += 1
        out = (out + " " + w) if out else w.capitalize()
    out = out[:n].rstrip()
    while len(out) < n:          # pad by lengthening the last word
        out += "s"
    return out


def resolve(s):
    while "$ref" in s:
        extra = {k: v for k, v in s.items() if k != "$ref"}
        s = dict(D[s["$ref"].split("/")[-1]], **extra)
    return s


def fill(s, key=""):
    s = resolve(s)
    if "const" in s:
        return s["const"]
    if "enum" in s:
        return s["enum"][0]
    t = s.get("type")
    if t == "boolean":
        return True
    if t == "string":
        if key in ("source",):
            return "S1"
        if key == "date" and "pattern" in s:
            return "2026-10-22"
        if key == "id":
            return "S1"
        if key == "url":
            return "https://example.com/" + "a" * (s.get("maxLength", 40) - 20)
        if key == "value" and s.get("maxLength", 99) <= 8:
            return "12,500"[: s.get("maxLength", 6)]
        if key == "price":
            return "[PRICE]"
        return text(s.get("maxLength", 40))
    if t == "array":
        return [fill(s["items"], key) for _ in range(s.get("maxItems", 3))]
    if t == "object":
        out = {}
        for k, v in s.get("properties", {}).items():
            if k == "to_confirm":      # worst case: cite (longer markers); a few claims get to_confirm instead
                continue
            if k in ("layout", "$schema"):
                continue
            out[k] = fill(v, k)
        return out
    raise ValueError(s)


def slide(kind, **extra):
    s = fill(D[kind])
    s.update(extra)
    return s


def main(out):
    srcs = []
    for i in range(1, 25):
        s = fill(D["source"])
        s["id"] = f"S{i}"
        s["date"] = "2026-10-08"
        srcs.append(s)
    slides = [
        slide("cover", art="process_map"),
        slide("situation"),
        slide("divider"),
        slide("focus"),
        slide("outputs"),
        slide("deliverables"),
        slide("process"),
        slide("process", layout="steps"),
        slide("needs"),
        slide("team"),
        slide("commercials"),
        slide("closing"),
        slide("sources_slide"),
    ]
    # cite three different sources with long locators, so markers are at their widest
    def recite(node):
        if isinstance(node, dict):
            if "cite" in node:
                node["cite"] = [{"source": f"S{1 + (next(counter) % 24)}", "locator": "Sheet1 H9-H120 r14"} for _ in node["cite"]]
            for v in node.values():
                recite(v)
        elif isinstance(node, list):
            for v in node:
                recite(v)
    recite(slides)
    # one point uses to_confirm, the other path for a claim
    slides[1]["points"][2].pop("cite")
    slides[1]["points"][2]["to_confirm"] = text(90)
    data = {"meta": {"title": text(90), "client": {"name": "Client A", "label": text(48)}, "date": "2026-10-22",
                     "status": text(40), "confidential": text(30)},
            "sources": srcs, "slides": slides}
    Path(out).write_text(json.dumps(data, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(HERE / "qa" / "stress.json"))
