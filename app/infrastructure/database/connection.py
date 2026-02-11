from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from functools import wraps
from threading import Thread

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_database_settings
from app.core import get_logger

logger = get_logger(__name__)

_engine = None
_factory: sessionmaker[SessionWithAfterCommit] | None = None


def get_engine():
    global _engine
    if _engine is None:
        database = get_database_settings()
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


class SessionWithAfterCommit(Session):
    """after_commit 훅을 지원하는 Session.

    async_hooks=True(기본): 훅을 별도 스레드에서 비동기 실행.
    async_hooks=False: 동기 실행 (테스트용).
    """

    def __init__(self, *args, async_hooks: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self._after_commit_hooks = []
        self._async_hooks = async_hooks

    def after_commit(self, fn: Callable[[], None]) -> None:
        self._after_commit_hooks.append(fn)

    def _execute_after_commit_hooks(self):
        for hook in self._after_commit_hooks:
            if self._async_hooks:
                Thread(target=self._run_hook, args=(hook,), daemon=True).start()
            else:
                self._run_hook(hook)
        self._after_commit_hooks.clear()

    @staticmethod
    def _run_hook(hook: Callable[[], None]) -> None:
        try:
            hook()
        except Exception:  # 안전망: hook은 임의의 callable — 데몬 스레드 크래시 방지
            logger.exception("after_commit_hook_failed")


SessionFactory = Callable[[], AbstractContextManager[SessionWithAfterCommit]]


def _setup_listeners():
    @event.listens_for(SessionWithAfterCommit, "after_commit")
    def receive_after_commit(session: SessionWithAfterCommit):
        session._execute_after_commit_hooks()

    @event.listens_for(SessionWithAfterCommit, "after_soft_rollback")
    def receive_after_rollback(session: SessionWithAfterCommit, _previous_transaction):
        session._after_commit_hooks.clear()


_setup_listeners()


def _get_factory() -> sessionmaker[SessionWithAfterCommit]:
    global _factory
    if _factory is None:
        _factory = sessionmaker(
            class_=SessionWithAfterCommit,
            bind=get_engine(),
            expire_on_commit=False,
        )
    return _factory


def get_session() -> AbstractContextManager[SessionWithAfterCommit]:
    return _get_factory().begin()


def transactional[**P, T](fn: Callable[P, T]) -> Callable[P, T]:
    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        with get_session() as session:
            return fn(session, *args, **kwargs)

    return wrapper
