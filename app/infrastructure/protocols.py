"""Infrastructure Protocol definitions.

서비스 레이어에서 인프라 의존성을 추상화하기 위한 Protocol 인터페이스.
테스트에서 Fake 구현체를 주입하여 외부 의존성 없이 테스트 가능.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.models import SettlementRow


@runtime_checkable
class SpreadsheetGateway(Protocol):
    """Google Sheets 스프레드시트 접근 프로토콜."""

    def save_settlement_row(
        self,
        row: SettlementRow,
        sheet_name: str | None = None,
        *,
        is_update: bool = False,
    ) -> None: ...

    def append_issue_log_row(self, row: SettlementRow, sync_key: str) -> None: ...

    def find_row_by_booking_key(
        self, booking_key: str, sheet_name: str | None = None
    ) -> int | None: ...
