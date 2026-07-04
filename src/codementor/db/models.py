from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel


class PullRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner: str
    repo: str
    pr_number: int
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewThread(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    pr_id: int = Field(foreign_key="pullrequest.id")
    student_id: str
    status: str = "completed"
    primary_issue: str
    severity: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AgentOutput(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    thread_id: int = Field(foreign_key="reviewthread.id")
    agent: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LearningPoint(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    thread_id: int = Field(foreign_key="reviewthread.id")
    concept: str
    difficulty: str
    reason: str
    kind: str = "learning_point"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ThreadMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    thread_id: int = Field(foreign_key="reviewthread.id")
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MiniTestat(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    thread_id: int = Field(foreign_key="reviewthread.id")
    questions_json: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
