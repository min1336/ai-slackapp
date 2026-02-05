from __future__ import annotations


class ActionId:
    OPEN_REGISTRATION_MODAL = "open_registration_modal"
    OPEN_TRANSFER_MODAL = "open_transfer_modal"  # 통합된 Transfer 모달 열기
    SETTLEMENT_APPROVE = "settlement_approve"
    SETTLEMENT_REJECT = "settlement_reject"
    SETTLEMENT_EDIT = "settlement_edit"
    TRANSFER_APPROVE = "transfer_approve"
    TRANSFER_REJECT = "transfer_reject"
    TRANSFER_EDIT = "transfer_edit"
    REGISTRATION_SUBMIT = "registration_submit"

    USER_NAME_INPUT = "user_name_input"
    BOOKING_KEY_INPUT = "booking_key_input"
    COMPANY_NAME_INPUT = "company_name_input"
    CUSTOMER_NAME_INPUT = "customer_name_input"
    SETTLEMENT_DAY_INPUT = "settlement_standard_day_input"
    ISSUE_TYPE_INPUT = "issue_type_input"
    COMPANY_SUB_NAME_INPUT = "company_sub_name_input"
    SETTLEMENT_COST_INPUT = "settlement_standard_cost_input"
    CARMORE_COST_INPUT = "carmore_cost_input"
    USER_REFUND_COST_INPUT = "user_refund_cost_input"
    SELLER_CHANNEL_INPUT = "seller_channel_input"
    DESCRIPTION_INPUT = "description_input"

    # 동적 폼용: "기타" 선택 시 텍스트 입력
    ISSUE_TYPE_TEXT_INPUT = "issue_type_text_input"
    DESCRIPTION_TEXT_INPUT = "description_text_input"

    # 비고 필드
    NOTE_INPUT = "note_input"


class BlockId:
    USER_NAME_BLOCK = "user_name_block"
    BOOKING_KEY_BLOCK = "booking_key_block"
    COMPANY_NAME_BLOCK = "company_name_block"
    CUSTOMER_NAME_BLOCK = "customer_name_block"
    SETTLEMENT_DAY_BLOCK = "settlement_standard_day_block"
    ISSUE_TYPE_BLOCK = "issue_type_block"
    COMPANY_SUB_NAME_BLOCK = "company_sub_name_block"
    SETTLEMENT_COST_BLOCK = "settlement_standard_cost_block"
    CARMORE_COST_BLOCK = "carmore_cost_block"
    USER_REFUND_COST_BLOCK = "user_refund_cost_block"
    SELLER_CHANNEL_BLOCK = "seller_channel_block"
    DESCRIPTION_BLOCK = "description_block"

    # 동적 폼용: "기타" 선택 시 텍스트 입력 블록
    ISSUE_TYPE_TEXT_BLOCK = "issue_type_text_block"
    DESCRIPTION_TEXT_BLOCK = "description_text_block"

    # 비고 필드
    NOTE_BLOCK = "note_block"


class CallbackId:
    REGISTRATION_SUBMIT = "registration_submit"
