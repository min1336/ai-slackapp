from __future__ import annotations

from app.constants import ActionId, BlockId, CommonText, HeaderText, LabelText
from app.constants.options import Description, IssueType
from app.views.blocks import (
    build_approval_request_message,
    build_approved_message,
    build_registration_modal,
    build_rejected_message,
)


class TestApprovalRequestMessage:
    def test_이관_설명일_때_transfer_action_id를_사용한다(self):
        blocks = build_approval_request_message(
            user_name="작성자",
            booking_key="BK-1",
            company_name="업체",
            customer_name="고객",
            settlement_day="2025-01-01",
            issue_type="이슈",
            settlement_cost="10000",
            company_sub_name="",
            carmore_cost="",
            user_refund_cost="",
            seller_channel="",
            description=Description.TRANSFER_RESERVATION.value,
            button_data="{}",
        )

        actions = blocks[-1]["elements"]
        assert actions[0]["action_id"] == ActionId.TRANSFER_APPROVE
        assert actions[1]["action_id"] == ActionId.TRANSFER_REJECT
        assert actions[2]["action_id"] == ActionId.TRANSFER_EDIT

    def test_빈_필드는_none_text로_표시한다(self):
        blocks = build_approval_request_message(
            user_name="",
            booking_key="",
            company_name="",
            customer_name="",
            settlement_day="",
            issue_type="",
            settlement_cost="",
            company_sub_name="",
            carmore_cost="",
            user_refund_cost="",
            seller_channel="",
            description="",
            button_data="{}",
        )

        first_section_fields = blocks[1]["fields"]
        assert first_section_fields[1]["text"] == CommonText.NONE
        assert first_section_fields[3]["text"] == CommonText.NONE


class TestDecisionMessage:
    def test_승인_메시지는_header_context를_갱신한다(self):
        original_blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "원본"}},
            {"type": "actions", "elements": []},
        ]
        result = build_approved_message(original_blocks, "홍길동")

        assert result[0]["text"]["text"] == HeaderText.APPROVED
        assert result[-1]["elements"][0]["text"] == "승인자: *홍길동*"
        assert all(block["type"] != "actions" for block in result)

    def test_반려_메시지는_header_context를_갱신한다(self):
        original_blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "원본"}},
            {"type": "actions", "elements": []},
        ]
        result = build_rejected_message(original_blocks, "김반려")

        assert result[0]["text"]["text"] == HeaderText.REJECTED
        assert result[-1]["elements"][0]["text"] == "반려자: *김반려*"
        assert all(block["type"] != "actions" for block in result)

    def test_헤더가_없어도_결정_메시지를_생성한다(self):
        original_blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "x"}}]

        result = build_approved_message(original_blocks, "홍길동")

        assert result[0]["type"] == "header"
        assert result[0]["text"]["text"] == HeaderText.APPROVED


class TestModalBuilders:
    def test_registration_modal_빈_user_name은_대시로_표시한다(self):
        modal = build_registration_modal(
            user_name="",
            booking_key="BK-1",
            company_name="업체",
            customer_name="고객",
            metadata="{}",
        )

        user_section = modal["blocks"][2]["fields"][1]
        assert user_section["text"] == CommonText.NONE

    def test_통합_모달에서_대신배차_prefill_설정가능(self):
        """Transfer 모달 통합: issue_type으로 "대신배차" prefill 확인"""
        modal = build_registration_modal(
            user_name="작성자",
            booking_key="BK-1",
            company_name="",
            customer_name="고객",
            metadata="{}",
            issue_type=IssueType.INSTEAD_DISPATCH.value,
            company_sub_name="업체2",
            settlement_cost="10000",
            carmore_cost="0",
        )

        issue_type_input = next(
            block
            for block in modal["blocks"]
            if block.get("block_id") == BlockId.ISSUE_TYPE_BLOCK
        )
        initial_text = issue_type_input["element"]["initial_option"]["text"]["text"]
        assert initial_text == IssueType.INSTEAD_DISPATCH.value

    def test_비고_필드는_optional로_렌더링한다(self):
        """비고 필드가 optional로 포함되는지 확인"""
        modal = build_registration_modal(
            user_name="작성자",
            booking_key="BK-1",
            company_name="업체",
            customer_name="고객",
            metadata="{}",
            note="테스트 비고",
        )

        note_input = next(
            (
                block
                for block in modal["blocks"]
                if block.get("block_id") == BlockId.NOTE_BLOCK
            ),
            None,
        )
        assert note_input is not None
        assert note_input["optional"] is True
        assert note_input["element"]["initial_value"] == "테스트 비고"
        assert note_input["element"]["multiline"] is True

    def test_동적폼_기타_선택시_텍스트_입력_블록으로_전환(self):
        """show_issue_type_text=True일 때 텍스트 입력 블록 렌더링"""
        modal = build_registration_modal(
            user_name="작성자",
            booking_key="BK-1",
            company_name="업체",
            customer_name="고객",
            metadata="{}",
            show_issue_type_text=True,
            custom_issue_type="커스텀 이슈",
        )

        # 텍스트 입력 블록이 있어야 함
        text_input = next(
            (
                block
                for block in modal["blocks"]
                if block.get("block_id") == BlockId.ISSUE_TYPE_TEXT_BLOCK
            ),
            None,
        )
        assert text_input is not None
        assert text_input["element"]["type"] == "plain_text_input"
        assert text_input["element"]["initial_value"] == "커스텀 이슈"

        # 셀렉트 블록이 없어야 함
        select_block = next(
            (
                block
                for block in modal["blocks"]
                if block.get("block_id") == BlockId.ISSUE_TYPE_BLOCK
            ),
            None,
        )
        assert select_block is None


class TestApprovalRequestMessageWithNote:
    def test_비고_필드가_표시된다(self):
        blocks = build_approval_request_message(
            user_name="작성자",
            booking_key="BK-1",
            company_name="업체",
            customer_name="고객",
            settlement_day="2025-01-01",
            issue_type="이슈",
            settlement_cost="10000",
            company_sub_name="",
            carmore_cost="",
            user_refund_cost="",
            seller_channel="",
            description="내용",
            button_data="{}",
            note="테스트 비고 내용",
        )

        # 마지막 섹션에 비고가 포함되어야 함
        text_section = next(
            block
            for block in blocks
            if block.get("type") == "section" and "text" in block
        )
        assert f"*{LabelText.NOTE}*" in text_section["text"]["text"]
        assert "테스트 비고 내용" in text_section["text"]["text"]
