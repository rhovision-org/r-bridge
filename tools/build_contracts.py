#!/usr/bin/env python3
"""Expand `// @@INLINE:path@@` markers in rholo deploy terms and enforce the size budget.

Deploy terms live under contracts/rholo/src/deploy. Fragments under
contracts/rholo/src/lib are inlined; they are not deployed directly. Output goes to
contracts/rholo/build and is committed so a change is reviewable. Placeholders
(__NETWORK__, __ADMINS__, ...) are left for harness/render.py to fill at deploy time.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "contracts" / "rholo" / "src"
DEPLOY = SRC / "deploy"
OUT = ROOT / "contracts" / "rholo" / "build"
MARKER = re.compile(r"^\s*//\s*@@INLINE:([^@]+)@@\s*$")
MAX_DEPTH = 12
TERM_BUDGET = 56 * 1024


class BuildError(RuntimeError):
    pass


def strip_strings(text: str) -> str:
    """Replace string literals with spaces so brace counting ignores them."""
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            out.append(" ")
        else:
            if ch == '"':
                in_string = True
                out.append(" ")
            else:
                out.append(ch)
    return "".join(out)


def check_braces(text: str, label: str) -> None:
    depth = 0
    for i, ch in enumerate(strip_strings(text)):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                raise BuildError(f"{label}: unbalanced '}}' at byte {i}")
    if depth != 0:
        raise BuildError(f"{label}: {depth} unclosed '{{'")


def inline(path: Path, stack: tuple[Path, ...] = ()) -> str:
    if len(stack) >= MAX_DEPTH:
        raise BuildError(f"inline depth exceeded at {path}")
    if path in stack:
        chain = " -> ".join(str(p.relative_to(ROOT)) for p in (*stack, path))
        raise BuildError(f"inline cycle: {chain}")
    lines: list[str] = []
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        match = MARKER.match(line)
        if not match:
            lines.append(line)
            continue
        target = SRC / match.group(1).strip()
        if not target.is_file():
            raise BuildError(f"{path}:{lineno}: missing inline target {target}")
        body = inline(target, (*stack, path))
        check_braces(body, str(target.relative_to(ROOT)))
        lines.append(body)
    return "\n".join(lines)


def build() -> dict[Path, str]:
    if not DEPLOY.is_dir():
        raise BuildError(f"missing {DEPLOY}")
    outputs: dict[Path, str] = {}
    for src in sorted(DEPLOY.glob("*.rho")):
        text = inline(src, ())
        check_braces(text, str(src.relative_to(ROOT)))
        size = len(text.encode("utf-8"))
        if size > TERM_BUDGET:
            raise BuildError(
                f"{src.name}: {size} bytes exceeds the {TERM_BUDGET}-byte budget"
            )
        outputs[OUT / src.name] = text.rstrip() + "\n"
    return outputs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail on drift instead of writing")
    args = ap.parse_args(argv)

    try:
        outputs = build()
    except BuildError as e:
        print(f"build-contracts: {e}", file=sys.stderr)
        return 1

    if args.check:
        stale: list[str] = []
        for path, text in outputs.items():
            if not path.is_file():
                stale.append(f"missing {path.relative_to(ROOT)}")
            elif path.read_text() != text:
                stale.append(f"drift {path.relative_to(ROOT)}")
        expected = {p.name for p in outputs}
        for path in OUT.glob("*.rho"):
            if path.name not in expected:
                stale.append(f"stale {path.relative_to(ROOT)}")
        if stale:
            for item in stale:
                print(f"build-contracts: {item}", file=sys.stderr)
            print("build-contracts: run `make build-contracts`", file=sys.stderr)
            return 1
        print(f"build-contracts: {len(outputs)} term(s) up to date")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    for path in OUT.glob("*.rho"):
        if path.name not in {p.name for p in outputs}:
            path.unlink()
    for path, text in outputs.items():
        path.write_text(text)
        print(f"build-contracts: wrote {path.relative_to(ROOT)} ({len(text.encode())} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
