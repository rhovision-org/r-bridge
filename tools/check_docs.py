#!/usr/bin/env python3
"""Check the mdBook structure and every relative link in the docs and README.

Checks:
  - every SUMMARY.md entry resolves, and every file under docs/src is in the summary;
  - every `{{#include ...}}` target resolves (including spec files outside docs/src);
  - every relative markdown link in docs/src, the included files and README.md resolves,
    ignoring links inside fenced code blocks and anchors/URLs.

Stdlib only. Exits non-zero with a file:line report on any failure.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SRC = DOCS / "src"
SUMMARY = SRC / "SUMMARY.md"
SUMMARY_LINK = re.compile(r"^\s*-\s+\[[^\]]*\]\(([^)]+)\)")
INCLUDE = re.compile(r"\{\{#include\s+([^}\s]+)\s*\}\}")
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
FENCE = re.compile(r"^\s*(```|~~~)")


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.files = 0
        self.links = 0
        self.includes = 0

    def fail(self, path: Path, line: int, message: str) -> None:
        try:
            shown = path.relative_to(ROOT)
        except ValueError:
            shown = path
        self.failures.append(f"{shown}:{line}: {message}")

    def check(self) -> int:
        if not SUMMARY.exists():
            self.fail(SUMMARY, 1, "missing SUMMARY.md")
            return self.report()
        summary_targets = self.check_summary()
        self.check_orphans(summary_targets)
        checked: set[Path] = set()
        included: set[Path] = set()
        for path in sorted(SRC.rglob("*.md")):
            checked.add(path)
            self.scan(path, included)
        readme = ROOT / "README.md"
        if readme.exists():
            checked.add(readme)
            self.scan(readme, included)
        for path in sorted(included):
            if path not in checked and path.suffix == ".md":
                checked.add(path)
                self.scan(path, set())
        self.files = len(checked)
        return self.report()

    def check_summary(self) -> set[Path]:
        targets: set[Path] = set()
        for number, line in enumerate(SUMMARY.read_text().splitlines(), start=1):
            match = SUMMARY_LINK.match(line)
            if not match:
                continue
            raw = match.group(1).strip()
            target = raw.split("#", 1)[0]
            if not target:
                self.fail(SUMMARY, number, f"empty summary link {raw!r}")
                continue
            path = (SRC / target).resolve()
            if not path.exists():
                self.fail(SUMMARY, number, f"summary target does not exist: {raw}")
                continue
            targets.add(path)
        return targets

    def check_orphans(self, targets: set[Path]) -> None:
        for path in sorted(SRC.rglob("*.md")):
            if path == SUMMARY:
                continue
            if path.resolve() not in targets:
                self.fail(path, 1, "file is not listed in SUMMARY.md")

    def scan(self, path: Path, included: set[Path]) -> None:
        text = path.read_text()
        in_fence = False
        for number, line in enumerate(text.splitlines(), start=1):
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            for match in INCLUDE.finditer(line):
                raw = match.group(1).strip()
                target = Path(raw.split(":", 1)[0])
                resolved = (path.parent / target).resolve()
                self.includes += 1
                if not resolved.exists():
                    self.fail(path, number, f"include target does not exist: {raw}")
                elif resolved.suffix == ".md":
                    included.add(resolved)
            if in_fence:
                continue
            for match in LINK.finditer(line):
                raw = match.group(1).strip()
                if raw.startswith("<") and raw.endswith(">"):
                    raw = raw[1:-1].strip()
                if self.is_external(raw):
                    continue
                self.links += 1
                target = raw.split("#", 1)[0].split("?", 1)[0]
                if not target:
                    continue
                if target.startswith("/"):
                    self.fail(path, number, f"absolute link is not portable: {raw}")
                    continue
                resolved = (path.parent / target).resolve()
                if not resolved.exists():
                    self.fail(path, number, f"link target does not exist: {raw}")

    @staticmethod
    def is_external(raw: str) -> bool:
        lowered = raw.lower()
        return (
            not raw
            or raw.startswith("#")
            or lowered.startswith(("http://", "https://", "mailto:", "tel:", "data:"))
        )

    def report(self) -> int:
        if self.failures:
            print(f"docs check: FAIL ({len(self.failures)} problem(s))")
            for failure in self.failures:
                print(f"  {failure}")
            return 1
        print(
            f"docs check: PASS ({self.files} files, {self.links} links, "
            f"{self.includes} includes)"
        )
        return 0


def main() -> int:
    return Checker().check()


if __name__ == "__main__":
    raise SystemExit(main())
