from __future__ import annotations


class LabelText:
    BOOKING_KEY = "예약번호"
    TRANSFER_BOOKING_KEY = "이관전 예약번호"  # 이관 예약용
    COMPANY_NAME = "업체명"
    CUSTOMER_NAME = "고객명"
    USER_NAME = "이슈 등록자"
    BOOKER_NAME = "예약자명"
    SETTLEMENT_DAY = "정산기준일"
    ISSUE_TYPE = "이슈사항"
    COMPANY_SUB_NAME = "업체명2(대신배차)"
    SETTLEMENT_COST = "정산기준금액"
    PRINCIPAL = "원금"  # 이관 예약용
    CARMORE_COST = "카모아 부담비용"
    CARMORE_BURDEN = "카모아 부담금"  # 이관 예약용 (다른 표현)
    USER_REFUND_COST = "고객 환불 금액"
    SELLER_CHANNEL = "판매채널"
    DESCRIPTION = "내용"
    NOTE = "비고"


class CommonText:
    NONE = "-"
    SELECT = "선택해주세요"
    SELECT_DATE = "날짜 선택"
    REGISTER = "등록"
    EDIT = "수정"
    MODIFIED = "수정됨"
    CANCEL = "취소"
    APPROVE = "승인"
    REJECT = "반려"
    REQUIRED = "(필수항목)"


class Command:
    SETTLEMENT_ISSUE = "!정산이슈"


class HeaderText:
    BOOKING_INFO = "📋 예약 정보"
    SETTLEMENT_ISSUE_REGISTER = "정산 이슈를 등록합니다"
    TRANSFER_REGISTER = "업체 이관을 등록합니다"
    SETTLEMENT_ISSUE_EDIT = "정산 이슈 수정"
    SETTLEMENT_ISSUE_NEW = "정산 이슈 등록"
    APPROVED = "승인 완료되었습니다 ✅"
    REJECTED = "반려되었습니다 ❌"
