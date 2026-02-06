"""테스트 데이터 팩토리"""

from __future__ import annotations

from app.models import SettlementData


class SettlementDataFactory:
    """SettlementData 테스트 인스턴스 생성 팩토리.

    기본값을 제공하여 테스트에서 관심 있는 필드만 오버라이드할 수 있게 합니다.

    Usage::

        data = SettlementDataFactory.create()                        # 기본값
        data = SettlementDataFactory.create(settlement_cost=50000)   # 금액만 변경
    """

    DEFAULTS: dict = {
        "user_name": "홍길동",
        "booking_key": "BK-001",
        "company_name": "카모아",
        "customer_name": "김철수",
        "issue_type": "정산제외",
        "settlement_day": "2025-01-01",
        "requester_id": "U123456",
    }

    @classmethod
    def create(cls, **overrides) -> SettlementData:
        """기본값에 overrides를 적용한 SettlementData 생성."""
        return SettlementData(**(cls.DEFAULTS | overrides))
