from __future__ import annotations

import re

from codementor.ci.findings import Finding


MYPY_LINE_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s*(?P<kind>error|note):\s*(?P<message>.+)$"
)

def parse_mypy_output(raw_text: str) -> list[Finding]:
    findings: list[Finding] = []
    for line in raw_text.splitlines():
        match = MYPY_LINE_RE.match(line.strip())
        if not match:
            continue
        kind = match.group("kind")
        severity = "error" if kind == "error" else "warning"
        #normalisierung
        findings.append(
            Finding(
                tool="mypy",
                file=match.group("file"),
                line=int(match.group("line")),
                message=match.group("message"),
                severity=severity,
            )
        )
    return findings
