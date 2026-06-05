from __future__ import annotations

from codementor.ci.parse_mypy import parse_mypy_output
from codementor.ci.parse_pytest import parse_pytest_output
from codementor.ci.parse_ruff import parse_ruff_output
from codementor.tools import ci_tools


def test_parse_ruff_output_handles_json_list() -> None:
    raw = (
        "[{\"filename\": \"src/app.py\", \"location\": {\"row\": 4}, "
        "\"code\": \"F401\", \"message\": \"unused import\"}]"
    )
    findings = parse_ruff_output(raw)

    assert len(findings) == 1
    assert findings[0].file == "src/app.py"
    assert findings[0].line == 4
    assert findings[0].severity == "error"


def test_parse_mypy_output_handles_errors_and_notes() -> None:
    raw = (
        "src/app.py:10: error: Argument 1 has incompatible type [arg-type]\n"
        "src/app.py:12: note: See docs"
    )
    findings = parse_mypy_output(raw)

    assert len(findings) == 2
    assert findings[0].severity == "error"
    assert findings[1].severity == "warning"


def test_parse_pytest_output_handles_failures() -> None:
    raw = (
        "{\"tests\": [{\"nodeid\": \"tests/test_app.py::test_one\", "
        "\"outcome\": \"failed\", "
        "\"call\": {\"longrepr\": \"assert 1 == 2\", "
        "\"crash\": {\"path\": \"tests/test_app.py\", \"lineno\": 5}}}]}"
    )
    findings = parse_pytest_output(raw)

    assert len(findings) == 1
    assert findings[0].file == "tests/test_app.py"
    assert findings[0].line == 5
    assert "assert 1 == 2" in findings[0].message


def test_parse_outputs_return_empty_on_invalid_json() -> None:
    assert parse_ruff_output("not-json") == []
    assert parse_pytest_output("not-json") == []


def test_parse_artifacts_handles_missing_files() -> None:
    payload = {
        "ruff.json": b"[]",
    }
    findings = ci_tools._parse_artifacts(payload)

    assert findings["ruff"] == []
    assert findings["mypy"] == []
    assert findings["pytest"] == []
