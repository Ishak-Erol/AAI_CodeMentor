from __future__ import annotations

import json

from sqlmodel import select

from codementor.config import get_config
from codementor.db.engine import get_engine, get_session
from codementor.db.models import (
    AgentOutput,
    LearningPoint,
    MiniTestat,
    PullRequest,
    ReviewThread,
    ThreadMessage,
)
from codementor.models import LearningPoint as LearningPointModel


def _engine():
    return get_engine(get_config().db_path)


def create_pull_request(owner: str, repo: str, pr_number: int, title: str) -> PullRequest:
    with get_session(_engine()) as session:
        pull_request = PullRequest(owner=owner, repo=repo, pr_number=pr_number, title=title)
        session.add(pull_request)
        session.commit()
        session.refresh(pull_request)
        return pull_request


def get_or_create_pull_request(owner: str, repo: str, pr_number: int, title: str) -> PullRequest:
    with get_session(_engine()) as session:
        statement = select(PullRequest).where(
            PullRequest.owner == owner,
            PullRequest.repo == repo,
            PullRequest.pr_number == pr_number,
        )
        existing = session.exec(statement).first()
        if existing is not None:
            return existing
        pull_request = PullRequest(owner=owner, repo=repo, pr_number=pr_number, title=title)
        session.add(pull_request)
        session.commit()
        session.refresh(pull_request)
        return pull_request


def create_thread(pr_id: int, primary_issue: str, severity: str, student_id: str) -> ReviewThread:
    with get_session(_engine()) as session:
        thread = ReviewThread(
            pr_id=pr_id,
            student_id=student_id,
            primary_issue=primary_issue,
            severity=severity,
        )
        session.add(thread)
        session.commit()
        session.refresh(thread)
        return thread


def save_agent_output(thread_id: int, agent: str, content: str) -> AgentOutput:
    with get_session(_engine()) as session:
        output = AgentOutput(thread_id=thread_id, agent=agent, content=content)
        session.add(output)
        session.commit()
        session.refresh(output)
        return output


def save_learning_points(
    thread_id: int, points: list[LearningPointModel]
) -> list[LearningPoint]:
    with get_session(_engine()) as session:
        saved: list[LearningPoint] = []
        for point in points:
            entry = LearningPoint(
                thread_id=thread_id,
                concept=point.concept,
                difficulty=point.difficulty,
                reason=point.reason,
                kind=point.kind,
            )
            session.add(entry)
            saved.append(entry)
        session.commit()
        for entry in saved:
            session.refresh(entry)
        return saved


def save_thread_message(thread_id: int, role: str, content: str) -> ThreadMessage:
    with get_session(_engine()) as session:
        message = ThreadMessage(thread_id=thread_id, role=role, content=content)
        session.add(message)
        session.commit()
        session.refresh(message)
        return message


def get_thread(thread_id: int) -> ReviewThread | None:
    with get_session(_engine()) as session:
        return session.get(ReviewThread, thread_id)


def list_threads(limit: int = 50, student_id: str | None = None) -> list[ReviewThread]:
    with get_session(_engine()) as session:
        statement = select(ReviewThread).order_by(ReviewThread.created_at.desc()).limit(limit)
        if student_id is not None:
            statement = statement.where(ReviewThread.student_id == student_id)
        return list(session.exec(statement).all())


def get_thread_messages(thread_id: int) -> list[ThreadMessage]:
    with get_session(_engine()) as session:
        statement = (
            select(ThreadMessage)
            .where(ThreadMessage.thread_id == thread_id)
            .order_by(ThreadMessage.timestamp)
        )
        return list(session.exec(statement).all())


def get_thread_learning_points(thread_id: int) -> list[LearningPoint]:
    with get_session(_engine()) as session:
        statement = select(LearningPoint).where(LearningPoint.thread_id == thread_id)
        return list(session.exec(statement).all())


def get_thread_agent_outputs(thread_id: int) -> list[AgentOutput]:
    with get_session(_engine()) as session:
        statement = (
            select(AgentOutput)
            .where(AgentOutput.thread_id == thread_id)
            .order_by(AgentOutput.timestamp)
        )
        return list(session.exec(statement).all())


def count_completed_threads(student_id: str) -> int:
    with get_session(_engine()) as session:
        statement = select(ReviewThread).where(
            ReviewThread.student_id == student_id,
            ReviewThread.status == "completed",
        )
        return len(session.exec(statement).all())


def get_recent_learning_points(
    student_id: str, limit_threads: int = 3
) -> list[LearningPoint]:
    with get_session(_engine()) as session:
        thread_statement = (
            select(ReviewThread)
            .where(ReviewThread.student_id == student_id)
            .order_by(ReviewThread.created_at.desc())
            .limit(limit_threads)
        )
        threads = session.exec(thread_statement).all()
        thread_ids = [thread.id for thread in threads]
        if not thread_ids:
            return []
        points_statement = select(LearningPoint).where(
            LearningPoint.thread_id.in_(thread_ids)
        )
        return list(session.exec(points_statement).all())


def save_mini_testat(thread_id: int, questions: list[dict]) -> MiniTestat:
    with get_session(_engine()) as session:
        testat = MiniTestat(thread_id=thread_id, questions_json=json.dumps(questions))
        session.add(testat)
        session.commit()
        session.refresh(testat)
        return testat


def get_mini_testat(thread_id: int) -> MiniTestat | None:
    with get_session(_engine()) as session:
        statement = select(MiniTestat).where(MiniTestat.thread_id == thread_id)
        return session.exec(statement).first()
