from __future__ import annotations


class ActionId:
    OPEN_REGISTRATION_MODAL = "open_registration_modal"
    OPEN_TRANSFER_REGISTRATION_MODAL = "open_transfer_registration_modal"
    SETTLEMENT_APPROVE = "settlement_approve"
    SETTLEMENT_REJECT = "settlement_reject"
    SETTLEMENT_EDIT = "settlement_edit"
    REGISTRATION_SUBMIT = "registration_submit"

    SETTLEMENT_DAY_INPUT = "settlement_standard_day_input"
    ISSUE_TYPE_INPUT = "issue_type_input"
    COMPANY_SUB_NAME_INPUT = "company_sub_name_input"
    SETTLEMENT_COST_INPUT = "settlement_standard_cost_input"
    CARMORE_COST_INPUT = "carmore_cost_input"
    USER_REFUND_COST_INPUT = "user_refund_cost_input"
    SELLER_CHANNEL_INPUT = "seller_channel_input"
    DESCRIPTION_INPUT = "description_input"


class BlockId:
    SETTLEMENT_DAY_BLOCK = "settlement_standard_day_block"
    ISSUE_TYPE_BLOCK = "issue_type_block"
    COMPANY_SUB_NAME_BLOCK = "company_sub_name_block"
    SETTLEMENT_COST_BLOCK = "settlement_standard_cost_block"
    CARMORE_COST_BLOCK = "carmore_cost_block"
    USER_REFUND_COST_BLOCK = "user_refund_cost_block"
    SELLER_CHANNEL_BLOCK = "seller_channel_block"
    DESCRIPTION_BLOCK = "description_block"


class CallbackId:
    REGISTRATION_SUBMIT = "registration_submit"
