from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codementor.config import get_config
from codementor.graph import build_review_graph
from codementor.github.client import GitHubClient, GitHubClientError
from codementor.github.copilot import extract_copilot_comments
from codementor.llm import LLMClientError, MockLLMClient, OpenAICompatibleLLMClient
from codementor.mock_loader import load_mock_review_state
from codementor.models import parse_reflection_decision
from codementor.rag import get_rag_context
from codementor.state import create_initial_state
from codementor.tools.ci_tools import get_ci_results
from codementor.tools.github_tools import get_pr_data


def _json_default(value: Any) -> str:
    return str(value)


def _get_llm_client(config, enabled: bool):
    if not enabled:
        return MockLLMClient()
    return OpenAICompatibleLLMClient(
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        model=config.llm_model,
    )


def run_mock(
    llm_client,
    rag_enabled: bool = False,
    rag_refresh: bool = False,
) -> dict[str, Any]:
    config = get_config()
    state = load_mock_review_state()
    if rag_enabled:
        rag_context = get_rag_context(
            state["pr_data"],
            state["ci_findings"],
            state["copilot_comments"],
            config,
            refresh=rag_refresh,
        )
        state["rag_context"] = rag_context
    graph = build_review_graph(llm=llm_client)
    final_state = graph.invoke(state)
    return dict(final_state)


def run_github(
    owner: str,
    repo: str,
    pr_number: int,
    llm_client,
    rag_enabled: bool = False,
    rag_refresh: bool = False,
) -> dict[str, Any]:
    config = get_config()
    if not config.github_token:
        raise GitHubClientError("GITHUB_TOKEN is required for --mode github.")

    client = GitHubClient(
        token=config.github_token,
        base_url=config.github_api_base_url,
    )
    pr_payload = get_pr_data(
        mode="github",
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        client=client,
        config=config,
    )
    pr_data = pr_payload["pr_data"]
    reviews = pr_payload["reviews"]
    review_comments = pr_payload["review_comments"]
    copilot_comments = extract_copilot_comments(
        reviews,
        review_comments,
        config.copilot_author_allowlist,
    )
    head_sha = pr_data.get("metadata", {}).get("head_sha")
    ci_findings = get_ci_results(
        mode="github",
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        head_sha=head_sha,
        client=client,
        config=config,
    )
    rag_context: list[dict[str, Any]] = []
    if rag_enabled:
        rag_context = get_rag_context(
            pr_data,
            ci_findings,
            copilot_comments,
            config,
            refresh=rag_refresh,
        )
    state = create_initial_state(pr_data, ci_findings, copilot_comments, rag_context)
    graph = build_review_graph(llm=llm_client)
    final_state = graph.invoke(state) # graph wird komplett ausgeführt
    return dict(final_state)


def main() -> int:
    parser = argparse.ArgumentParser(description="Team CodeMentor Sprint 2 CLI")
    parser.add_argument(
        "--mode",
        default="mock",
        choices=["mock", "github"],
        help="Execution mode. Use github for live GitHub PR analysis.",
    )
    parser.add_argument("--owner", help="GitHub owner or organization.")
    parser.add_argument("--repo", help="GitHub repository name.")
    parser.add_argument("--pr", type=int, help="Pull request number.")
    parser.add_argument(
        "--rag",
        action="store_true",
        help="Enable RAG retrieval from technical documentation.",
    )
    parser.add_argument(
        "--rag-refresh",
        action="store_true",
        help="Force re-indexing of documentation sources.",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Enable live LLM calls using the AcademicCloud API.",
    )
    args = parser.parse_args()

    config = get_config()
    rag_enabled = args.rag or config.rag_enabled
    llm_enabled = args.llm or config.llm_enabled
    try:
        llm_client = _get_llm_client(config, llm_enabled)
    except LLMClientError as exc:
        print(f"LLM error: {exc}")
        return 2

    if args.mode == "mock":
        final_state = run_mock(
            llm_client=llm_client,
            rag_enabled=rag_enabled,
            rag_refresh=args.rag_refresh,
        )
    else:
        if not (args.owner and args.repo and args.pr):
            print("Error: --mode github requires --owner, --repo, and --pr.")
            return 2
        try:
            final_state = run_github(
                args.owner,
                args.repo,
                args.pr,
                llm_client=llm_client,
                rag_enabled=rag_enabled,
                rag_refresh=args.rag_refresh,
            )
        except GitHubClientError as exc:
            print(f"GitHub error: {exc}")
            return 2
    
    decision = parse_reflection_decision(final_state["reflection_decision"]) # ergebnis von reflection agent
    # learning points sind array 
    learning_points = final_state.get("learning_points", [])

    mode_label = "mock" if args.mode == "mock" else "github"
    print(f"Team CodeMentor Sprint 2 {mode_label} run completed.")
    print(
        "Summary: "
        f"primary_issue={decision.primary_issue}, "
        f"severity={decision.severity}, "
        f"learning_points={len(learning_points)}"
    )
    print("FINAL_STATE_JSON:")
    print(json.dumps(final_state, indent=2, ensure_ascii=False, default=_json_default))
    with open("last_run.json", "w", encoding="utf-8") as f:
        json.dump(final_state, f, indent=2, ensure_ascii=False, default=_json_default)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
