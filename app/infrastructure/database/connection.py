from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import wraps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import database
from app.core import get_logger

logger = get_logger(__name__)

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        if not database.url:
            raise ValueError("DATABASE_URL is not configured")
        _engine = create_engine(
            database.url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=300,  # 5분마다 연결 재생성 (Supabase idle timeout 대응)
            echo=False,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
        )
    return _session_factory


class SessionWithAfterCommit(Session):
    """after_commit 훅을 지원하는 Session."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._after_commit_hooks: list[Callable[[], None]] = []

    def after_commit(self, fn: Callable[[], None]) -> None:
        """커밋 후 실행할 함수 등록."""
        self._after_commit_hooks.append(fn)

    def _execute_after_commit_hooks(self):
        """등록된 after_commit 훅들 실행."""
        for hook in self._after_commit_hooks:
            try:
                hook()
            except Exception as e:
                logger.warning("after_commit_hook_failed", error=str(e))
        self._after_commit_hooks.clear()


def _setup_after_commit_listener():
    """Session의 after_commit 이벤트 리스너 설정."""

    @event.listens_for(SessionWithAfterCommit, "after_commit")
    def receive_after_commit(session: SessionWithAfterCommit):
        session._execute_after_commit_hooks()


_setup_after_commit_listener()


@contextmanager
def get_session() -> Generator[SessionWithAfterCommit, None, None]:
    """데이터베이스 세션 (자동 트랜잭션 관리)."""
    session = SessionWithAfterCommit(bind=get_engine(), expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        session._after_commit_hooks.clear()
        raise
    finally:
        session.close()


def transactional[**P, T](fn: Callable[P, T]) -> Callable[P, T]:
    """첫 번째 파라미터(session)를 자동 주입. 호출 시 session 생략."""

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        with get_session() as session:
            return fn(session, *args, **kwargs)

    return wrapper
