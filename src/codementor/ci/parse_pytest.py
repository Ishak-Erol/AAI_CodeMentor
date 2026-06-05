from __future__ import annotations

import json
from typing import Any

from codementor.ci.findings import Finding


def _extract_failure_details(test: dict[str, Any]) -> tuple[str, int, str]:
    call = test.get("call") or {}
    crash = call.get("crash") or {}
    path = crash.get("path") or test.get("path") or "unknown"
    line = crash.get("lineno") or 1
    message = call.get("longrepr") or test.get("nodeid") or "pytest failure"
    try:
        line_number = int(line)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        line_number = 1
    return str(path), line_number, str(message)


def parse_pytest_output(raw_text: str) -> list[Finding]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return []

    tests = payload.get("tests", []) if isinstance(payload, dict) else []
    findings: list[Finding] = []
    for test in tests:
        if not isinstance(test, dict):
            continue
        if test.get("outcome") != "failed":
            continue
        file, line, message = _extract_failure_details(test)
        findings.append(
            Finding(
                tool="pytest",
                file=file,
                line=line,
                message=message,
                severity="error",
            )
        )
    return findings
