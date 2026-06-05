from __future__ import annotations

import json
from codementor.ci.findings import Finding


def _severity_from_code(code: str | None) -> str:
    if not code:
        return "warning"
    if code.startswith("E") or code.startswith("F"):
        return "error"
    return "warning"


def _to_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1


def parse_ruff_output(raw_text: str) -> list[Finding]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return []

    if isinstance(payload, dict):
        issues = payload.get("diagnostics", [])
    elif isinstance(payload, list):
        issues = payload
    else:
        return []

    findings: list[Finding] = []
    for item in issues:
        if not isinstance(item, dict):
            continue
        location = item.get("location") or {}
        row = location.get("row") or item.get("row") or 1
        findings.append(
            Finding(
                tool="ruff",
                file=str(item.get("filename") or item.get("file") or "unknown"),
                line=_to_int(row),
                message=str(item.get("message") or ""),
                severity=_severity_from_code(item.get("code")),
            )
        )
    return findings
