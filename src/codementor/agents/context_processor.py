from typing import Any
from codementor.state import ReviewState

def analyze_context(state: ReviewState) -> dict[str, Any]:
    # 3.1 & 3.4: Problemkontext ableiten und RAG-Trigger setzen
    findings = state["ci_findings"]
    issue_category = "code_quality" # Default
    
    if findings.get("pytest"):
        issue_category = "testing"
    elif findings.get("mypy"):
        issue_category = "typing"
        
    return {
        "issue_category": issue_category,
        "rag_query": f"{issue_category} best practices python",
        "affected_files": [f["path"] for f in state["pr_data"].get("changed_files", [])]
    }