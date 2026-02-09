from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.database.repository import ThreadReferenceRepository
from app.models import ThreadLocation
from app.services.thread_discovery_service import (
    find_issue_thread,
    register_origin_thread,
    save_thread_reference,
)
from tests.fakes.fake_database import FakeDatabase


@pytest.fixture
def fake_db():
    return FakeDatabase()


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.slack_channels.reservation = "C_ISSUE"
    with patch(
        "app.services.thread_discovery_service.get_app_config",
        return_value=config,
    ):
        yield config


class TestFindIssueThread:
    def test_채널_미설정시_None_반환(self, mock_client, fake_db):
        config = MagicMock()
        config.slack_channels.reservation = ""
        with patch(
            "app.services.thread_discovery_service.get_app_config",
            return_value=config,
        ):
            result = find_issue_thread(
                "BK-001",
                mock_client,
                session_factory=fake_db.get_session,
            )

        assert result is None

    def test_DB에_있으면_즉시_반환(self, mock_client, mock_config, fake_db):
        # Given — DB에 레퍼런스 저장
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            repo.save(
                booking_key="BK-001",
                channel_id="C_ISSUE",
                thread_ts="111.111",
            )

        # When
        result = find_issue_thread(
            "BK-001",
            mock_client,
            session_factory=fake_db.get_session,
        )

        # Then
        assert result == ThreadLocation(channel_id="C_ISSUE", thread_ts="111.111")

    @patch("app.services.thread_discovery_service.find_message_by_text")
    def test_DB_미스시_Slack_API_폴백(
        self, mock_find, mock_client, mock_config, fake_db
    ):
        mock_find.return_value = "222.222"

        result = find_issue_thread(
            "BK-001",
            mock_client,
            session_factory=fake_db.get_session,
        )

        assert result == ThreadLocation(channel_id="C_ISSUE", thread_ts="222.222")
        mock_find.assert_called_once_with(mock_client, "C_ISSUE", "BK-001")

    @patch("app.services.thread_discovery_service.find_message_by_text")
    def test_Slack_API_폴백_후_DB에_캐시_저장(
        self, mock_find, mock_client, mock_config, fake_db
    ):
        mock_find.return_value = "333.333"

        find_issue_thread(
            "BK-001",
            mock_client,
            session_factory=fake_db.get_session,
        )

        # DB에 캐시되었는지 확인
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("BK-001")
            assert ref is not None
            assert ref.thread_ts == "333.333"
            assert ref.channel_id == "C_ISSUE"

    @patch("app.services.thread_discovery_service.find_message_by_text")
    def test_Slack_API에서도_못_찾으면_None(
        self, mock_find, mock_client, mock_config, fake_db
    ):
        mock_find.return_value = None

        result = find_issue_thread(
            "BK-001",
            mock_client,
            session_factory=fake_db.get_session,
        )

        assert result is None


class TestSaveThreadReference:
    def test_기본_저장(self, fake_db):
        save_thread_reference(
            booking_key="BK-001",
            channel_id="C123",
            thread_ts="111.111",
            session_factory=fake_db.get_session,
        )

        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("BK-001")
            assert ref is not None
            assert ref.root_booking_key == "BK-001"

    def test_root_booking_key_지정(self, fake_db):
        save_thread_reference(
            booking_key="BK-002",
            channel_id="C123",
            thread_ts="111.111",
            root_booking_key="BK-001",
            session_factory=fake_db.get_session,
        )

        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("BK-002")
            assert ref is not None
            assert ref.root_booking_key == "BK-001"


class TestRegisterOriginThread:
    def test_최초_스레드_등록(self, fake_db):
        register_origin_thread(
            booking_key="BK-001",
            channel_id="C_ISSUE",
            thread_ts="111.111",
            session_factory=fake_db.get_session,
        )

        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("BK-001")
            assert ref is not None
            assert ref.channel_id == "C_ISSUE"
            assert ref.thread_ts == "111.111"
            assert ref.root_booking_key == "BK-001"

    def test_중복_등록은_안전하게_무시된다(self, fake_db):
        for _ in range(3):
            register_origin_thread(
                booking_key="BK-001",
                channel_id="C_ISSUE",
                thread_ts="111.111",
                session_factory=fake_db.get_session,
            )

        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("BK-001")
            assert ref is not None
