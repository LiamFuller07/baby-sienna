#!/usr/bin/env python3
"""Resolve the Source theme policy and check its declared foundation tokens."""

import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parent.parent


def hostname(value):
    parsed = urlsplit(value if "://" in value else "https://" + value)
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        raise ValueError("Provide a hostname or HTTP(S) URL without credentials.")
    # Accessing .port rejects malformed or out-of-range ports.
    _ = parsed.port
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or not re.fullmatch(r"[a-z0-9.:-]+", host):
        raise ValueError("Invalid site hostname.")
    return host


def local(host):
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def classify(sites, local_source_app, policy):
    hosts = list(dict.fromkeys(hostname(site) for site in sites))
    protected = [
        host
        for host in hosts
        if any(host == excluded or host.endswith("." + excluded) for excluded in policy["excludedHosts"])
    ]
    if protected:
        return {
            "status": "exempt",
            "hosts": hosts,
            "theme": "preserve-existing",
            "reason": "Protected sales-site identity, including local and preview copies.",
        }
    domain = policy["domain"]
    eligible = any(host == domain or host.endswith("." + domain) for host in hosts)
    if eligible or (local_source_app and all(local(host) for host in hosts)):
        return {
            "status": "default",
            "hosts": hosts,
            "theme": policy["id"],
            "reason": "Use the shared Source application design.",
        }
    return {
        "status": "unresolved",
        "hosts": hosts,
        "theme": None,
        "reason": "Supply the canonical Source hostname; localhost or preview URL alone does not identify an app.",
    }


def declared_tokens(css):
    # Deliberately bounded: simple :root declarations, not a CSS cascade engine.
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    roots = re.findall(r":root\s*\{([^{}]*)\}", css, flags=re.S)
    if not roots:
        raise ValueError("No simple :root token block found in the supplied stylesheet.")
    values = {}
    for root in roots:
        values.update(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root))
    return values


def resolve(name, values, seen=()):
    if name in seen or name not in values:
        raise ValueError("Missing or circular token: " + name)
    return re.sub(
        r"var\(\s*(--[\w-]+)\s*\)", lambda match: resolve(match[1], values, (*seen, name)), values[name]
    ).strip()


def normalized(value):
    return re.sub(r"\s+", "", value).lower()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("scope", "tokens", "check"))
    parser.add_argument(
        "--site", action="append", default=[], help="Actual and/or canonical site; repeat for preview copies."
    )
    parser.add_argument(
        "--local-source-app",
        action="store_true",
        help="Only for a confirmed local Source app with no hosted identity.",
    )
    parser.add_argument("--output", type=Path, help="tokens: destination for the portable CSS.")
    parser.add_argument("--css", type=Path, help="check: the app's shared root stylesheet.")
    parser.add_argument("--adapter", choices=("sourcecore", "discovery"), default="sourcecore")
    args = parser.parse_args()
    policy = json.loads((BASE / "references/policy.json").read_text())
    scope = classify(args.site, args.local_source_app, policy)
    print(json.dumps(scope))
    if scope["status"] != "default":
        return 3 if scope["status"] == "exempt" else 2
    if args.action == "scope":
        return 0
    if args.action == "tokens":
        if not args.output:
            parser.error("tokens requires --output")
        content = (BASE / "assets/source-tokens.css").read_bytes()
        if args.output.is_symlink():
            raise ValueError("Refusing to replace a symlink.")
        if args.output.exists():
            if args.output.read_bytes() != content:
                raise ValueError("Destination differs; review its existing theme before changing it.")
            print("The portable token file is already current.")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("xb") as target:
                target.write(content)
            print("Installed tokens at " + str(args.output))
        print("Import this CSS in the app and retain the app's font and component setup.")
        return 0
    if not args.css:
        parser.error("check requires --css")
    values = declared_tokens(args.css.read_text())
    failures = []
    for token, expected in policy["coreTokens"].items():
        name = policy["adapters"][args.adapter].get(token, token)
        try:
            actual = resolve(name, values)
            if normalized(actual) != normalized(expected):
                failures.append(f"{name}: expected {expected}; found {actual}")
        except ValueError as error:
            failures.append(str(error))
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"PASS: {len(policy['coreTokens'])} declared foundation tokens match {policy['id']}.")
    print("This is a token check, not browser, integration, or deployment verification.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as error:
        print("Source design check: " + str(error), file=sys.stderr)
        sys.exit(1)
