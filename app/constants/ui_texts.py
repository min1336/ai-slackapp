from __future__ import annotations


class LabelText:
    BOOKING_KEY = "예약번호"
    COMPANY_NAME = "업체명"
    CUSTOMER_NAME = "고객명"
    USER_NAME = "이슈 등록자"
    BOOKER_NAME = "예약자명"
    SETTLEMENT_DAY = "정산기준일"
    ISSUE_TYPE = "이슈사항"
    COMPANY_SUB_NAME = "업체명2(대신배차)"
    SETTLEMENT_COST = "정산기준금액"
    CARMORE_COST = "카모아 부담비용"
    USER_REFUND_COST = "고객 환불 금액"
    SELLER_CHANNEL = "판매채널"
    DESCRIPTION = "내용"


class CommonText:
    NONE = "(없음)"
    SELECT = "선택하세요"
    SELECT_DATE = "날짜 선택"
    REGISTER = "등록"
    EDIT = "편집"
    MODIFIED = "수정"
    CANCEL = "취소"
    APPROVE = "승인"
    REJECT = "반려"
    REQUIRED = " (필수)"


class Command:
    SETTLEMENT_ISSUE = "!정산이슈"


class HeaderText:
    BOOKING_INFO = "📋 예약 정보"
    SETTLEMENT_ISSUE_REGISTER = "📝 정산 이슈를 등록하시겠습니까?"
    TRANSFER_REGISTER = "📝 업체이관을 등록하시겠습니까?"
    SETTLEMENT_ISSUE_EDIT = "정산 이슈 편집"
    SETTLEMENT_ISSUE_NEW = "정산 이슈 등록"
    APPROVED = "✅ 정산 이슈가 승인되었습니다."
    REJECTED = "❌ 정산 이슈가 반려되었습니다."
