"""settlement_service 비즈니스 로직 테스트"""

from __future__ import annotations

from app.models.settlement import SettlementStatus
from app.services.settlement_service import save_settlement
from tests.fakes.fake_spreadsheet import FakeSpreadsheet


class TestSaveSettlement:
    """save_settlement() 함수 테스트"""

    def test_승인시_시트에_저장한다(self, monkeypatch, sample_settlement_data):
        # Given
        fake_sheet = FakeSpreadsheet()

        monkeypatch.setattr(
            "app.services.settlement_service._save_row",
            fake_sheet.save_settlement_row,
        )
        monkeypatch.setattr(
            "app.services.settlement_service._append_log_row",
            fake_sheet.append_approval_log_row,
        )

        # When
        result = save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )

        # Then
        assert result is True
        assert sample_settlement_data.booking_key in fake_sheet.settlement_rows
        assert len(fake_sheet.approval_logs) == 1

    def test_반려시_저장하지_않고_성공_반환한다(
        self, monkeypatch, sample_settlement_data
    ):
        # Given
        fake_sheet = FakeSpreadsheet()

        monkeypatch.setattr(
            "app.services.settlement_service._save_row",
            fake_sheet.save_settlement_row,
        )
        monkeypatch.setattr(
            "app.services.settlement_service._append_log_row",
            fake_sheet.append_approval_log_row,
        )

        # When
        result = save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.REJECTED,
            approver_name="반려자",
            thread_url="http://example.com/thread",
        )

        # Then
        assert result is True
        # 반려 시에는 저장하지 않음
        assert sample_settlement_data.booking_key not in fake_sheet.settlement_rows
        assert len(fake_sheet.approval_logs) == 0

    def test_시트_저장_실패시_False_반환한다(self, monkeypatch, sample_settlement_data):
        # Given
        fake_sheet = FakeSpreadsheet()
        fake_sheet.should_fail = True

        monkeypatch.setattr(
            "app.services.settlement_service._save_row",
            fake_sheet.save_settlement_row,
        )
        monkeypatch.setattr(
            "app.services.settlement_service._append_log_row",
            fake_sheet.append_approval_log_row,
        )

        # When
        result = save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )

        # Then
        assert result is False

    def test_승인시_settlement_row와_approval_log_모두_저장한다(
        self, monkeypatch, sample_settlement_data
    ):
        # Given
        fake_sheet = FakeSpreadsheet()

        monkeypatch.setattr(
            "app.services.settlement_service._save_row",
            fake_sheet.save_settlement_row,
        )
        monkeypatch.setattr(
            "app.services.settlement_service._append_log_row",
            fake_sheet.append_approval_log_row,
        )

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )

        # Then - 두 시트 모두에 저장됨
        assert len(fake_sheet.settlement_rows) == 1
        assert len(fake_sheet.approval_logs) == 1

    def test_저장된_데이터에_승인자_이름이_포함된다(
        self, monkeypatch, sample_settlement_data
    ):
        # Given
        fake_sheet = FakeSpreadsheet()
        approver = "김승인"

        monkeypatch.setattr(
            "app.services.settlement_service._save_row",
            fake_sheet.save_settlement_row,
        )
        monkeypatch.setattr(
            "app.services.settlement_service._append_log_row",
            fake_sheet.append_approval_log_row,
        )

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name=approver,
            thread_url="http://example.com/thread",
        )

        # Then - 저장된 row에 승인자 이름 포함
        saved_row = fake_sheet.settlement_rows[sample_settlement_data.booking_key]
        assert approver in saved_row
