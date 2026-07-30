from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine


@cache
def get_engine(db_path: str) -> Engine:
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )


def init_db(engine: Engine) -> None:
    import codementor.db.models  # noqa: F401  ensures models are registered on SQLModel.metadata

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
