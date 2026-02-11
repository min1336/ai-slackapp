from __future__ import annotations

from contextlib import AbstractContextManager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.connection import SessionWithAfterCommit
from app.infrastructure.database.models import Base


class FakeDatabase:
    def __init__(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self._factory = sessionmaker(
            class_=SessionWithAfterCommit,
            bind=self.engine,
            expire_on_commit=False,
            async_hooks=False,
        )

    def get_session(self) -> AbstractContextManager[SessionWithAfterCommit]:
        return self._factory.begin()

    def clear(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
