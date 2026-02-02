"""인메모리 데이터베이스 Fake (SQLite 사용)"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine

from app.infrastructure.database.connection import SessionWithAfterCommit
from app.infrastructure.database.models import Base


class FakeDatabase:
    """PostgreSQL 대신 사용할 인메모리 SQLite Fake

    테스트에서 실제 데이터베이스 연결을 이 Fake로 교체하여 사용합니다.
    각 테스트마다 새로운 인스턴스를 생성하면 격리된 상태로 테스트할 수 있습니다.
    """

    def __init__(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)

    @contextmanager
    def get_session(self) -> Generator[SessionWithAfterCommit, None, None]:
        """Get a database session with automatic transaction management.

        SessionWithAfterCommit을 사용하여 after_commit 훅을 지원합니다.
        """
        session = SessionWithAfterCommit(bind=self.engine, expire_on_commit=False)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            session._after_commit_hooks.clear()
            raise
        finally:
            session.close()

    def clear(self):
        """테스트 간 상태 초기화"""
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
