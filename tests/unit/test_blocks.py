from __future__ import annotations

from app.constants import ActionId, BlockId, CommonText, HeaderText, LabelText
from app.constants.options import Description, IssueType
from app.views.blocks import (
    build_approval_request_message,
    build_approved_message,
    build_minimal_approval_message,
    build_minimal_approved_message,
    build_minimal_processing_message,
    build_minimal_rejected_message,
    build_registration_modal,
    build_rejected_message,
    build_rejection_modal,
    build_transfer_parsing_result_message,
)
from tests.factories import SettlementDataFactory

_make_data = SettlementDataFactory.create


class TestApprovalRequestMessage:
    def test_이관_설명일_때_transfer_action_id를_사용한다(self):
        data = _make_data(
            settlement_cost=10000,
            description=Description.TRANSFER_RESERVATION.value,
        )
        blocks = build_approval_request_message(data, button_data="{}")

        actions = blocks[-1]["elements"]
        assert len(actions) == 2  # 승인/반려 버튼만 존재
        assert actions[0]["action_id"] == ActionId.TRANSFER_APPROVE
        assert actions[1]["action_id"] == ActionId.TRANSFER_REJECT

    def test_빈_필드는_none_text로_표시한다(self):
        data = _make_data(
            user_name="",
            booking_key="",
            company_name="",
            customer_name="",
            settlement_day="",
            issue_type="",
        )
        blocks = build_approval_request_message(data, button_data="{}")

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

    def test_동적폼_기타_선택시_셀렉트_유지_및_텍스트_입력_추가(self):
        """show_issue_type_text=True일 때 셀렉트 유지 + 텍스트 입력 블록 추가"""
        modal = build_registration_modal(
            user_name="작성자",
            booking_key="BK-1",
            company_name="업체",
            customer_name="고객",
            metadata="{}",
            show_issue_type_text=True,
            custom_issue_type="커스텀 이슈",
        )

        # 셀렉트 블록이 유지되어야 함
        select_block = next(
            (
                block
                for block in modal["blocks"]
                if block.get("block_id") == BlockId.ISSUE_TYPE_BLOCK
            ),
            None,
        )
        assert select_block is not None
        assert select_block["element"]["type"] == "static_select"
        # 셀렉트의 initial_option이 "기타"여야 함
        initial_text = select_block["element"]["initial_option"]["text"]["text"]
        assert initial_text == IssueType.OTHER.value

        # 텍스트 입력 블록도 있어야 함
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


class TestApprovalRequestMessageWithNote:
    def test_비고_필드가_표시된다(self):
        data = _make_data(
            settlement_cost=10000,
            description="내용",
            note="테스트 비고 내용",
        )
        blocks = build_approval_request_message(data, button_data="{}")

        # 마지막 섹션에 비고가 포함되어야 함
        text_section = next(
            block
            for block in blocks
            if block.get("type") == "section" and "text" in block
        )
        assert f"*{LabelText.NOTE}*" in text_section["text"]["text"]
        assert "테스트 비고 내용" in text_section["text"]["text"]


class TestRejectionModal:
    def test_반려_모달은_사유_입력_필드를_포함한다(self):
        modal = build_rejection_modal(metadata="{}")

        assert modal["type"] == "modal"
        assert modal["callback_id"] == ActionId.REJECTION_SUBMIT
        assert modal["title"]["text"] == HeaderText.REJECTION_MODAL

        # 반려 사유 입력 블록 확인
        reason_block = modal["blocks"][0]
        assert reason_block["block_id"] == BlockId.REJECTION_REASON_BLOCK
        assert reason_block["element"]["action_id"] == ActionId.REJECTION_REASON_INPUT
        assert reason_block["element"]["multiline"] is True


class TestRejectedMessageWithReason:
    def test_반려_메시지에_사유가_표시된다(self):
        original_blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "원본"}},
            {"type": "actions", "elements": []},
        ]
        result = build_rejected_message(
            original_blocks=original_blocks,
            rejecter_name="김반려",
            rejection_reason="테스트 반려 사유입니다",
        )

        # 헤더 변경 확인
        assert result[0]["text"]["text"] == HeaderText.REJECTED

        # 반려 사유 섹션 확인
        reason_section = next(
            (block for block in result if block.get("type") == "section"),
            None,
        )
        assert reason_section is not None
        assert f"*{LabelText.REJECTION_REASON}*" in reason_section["text"]["text"]
        assert "테스트 반려 사유입니다" in reason_section["text"]["text"]

        # 반려자 context 확인
        assert result[-1]["elements"][0]["text"] == "반려자: *김반려*"


# ============================================================================
# 승인 채널 통합 기능용 블록 빌더 테스트
# ============================================================================


class TestMinimalApprovalMessage:
    """승인 채널용 최소 정보 메시지 테스트"""

    def test_정산이슈_승인요청은_settlement_action_id를_사용한다(self):
        blocks = build_minimal_approval_message(
            requester_name="홍길동",
            thread_url="https://slack.com/archives/C123/p456",
            button_data="{}",
            is_transfer=False,
        )

        actions = blocks[-1]["elements"]
        assert len(actions) == 2
        assert actions[0]["action_id"] == ActionId.SETTLEMENT_APPROVE
        assert actions[1]["action_id"] == ActionId.SETTLEMENT_REJECT

    def test_업체이관_승인요청은_transfer_action_id를_사용한다(self):
        blocks = build_minimal_approval_message(
            requester_name="홍길동",
            thread_url="https://slack.com/archives/C123/p456",
            button_data="{}",
            is_transfer=True,
        )

        actions = blocks[-1]["elements"]
        assert len(actions) == 2
        assert actions[0]["action_id"] == ActionId.TRANSFER_APPROVE
        assert actions[1]["action_id"] == ActionId.TRANSFER_REJECT

    def test_요청자_이름이_표시된다(self):
        blocks = build_minimal_approval_message(
            requester_name="김요청",
            thread_url="https://slack.com/test",
            button_data="{}",
            is_transfer=False,
        )

        # 요청자 필드 확인
        requester_section = blocks[1]
        assert requester_section["fields"][0]["text"] == "*요청자*"
        assert requester_section["fields"][1]["text"] == "김요청"

    def test_스레드_링크가_표시된다(self):
        thread_url = "https://slack.com/archives/C123/p456"
        blocks = build_minimal_approval_message(
            requester_name="홍길동",
            thread_url=thread_url,
            button_data="{}",
            is_transfer=False,
        )

        link_section = blocks[2]
        assert thread_url in link_section["text"]["text"]
        assert "원본 스레드 바로가기" in link_section["text"]["text"]

    def test_헤더에_요청_유형이_표시된다(self):
        settlement_blocks = build_minimal_approval_message(
            requester_name="홍길동",
            thread_url="https://slack.com/test",
            button_data="{}",
            is_transfer=False,
        )
        assert "정산 이슈" in settlement_blocks[0]["text"]["text"]

        transfer_blocks = build_minimal_approval_message(
            requester_name="홍길동",
            thread_url="https://slack.com/test",
            button_data="{}",
            is_transfer=True,
        )
        assert "업체 이관" in transfer_blocks[0]["text"]["text"]


class TestMinimalApprovedMessage:
    """승인 채널 승인 완료 메시지 테스트"""

    def test_승인_완료_메시지에_취소선이_적용된다(self):
        blocks = build_minimal_approved_message(
            requester_name="홍길동",
            thread_url="https://slack.com/test",
            approver_name="김승인",
            is_transfer=False,
        )

        # 첫 번째 섹션에 취소선 (mrkdwn ~text~)
        header_section = blocks[0]
        assert header_section["text"]["type"] == "mrkdwn"
        assert "~*정산 이슈 승인 요청*~" in header_section["text"]["text"]

    def test_승인자_이름이_표시된다(self):
        blocks = build_minimal_approved_message(
            requester_name="홍길동",
            thread_url="https://slack.com/test",
            approver_name="박승인자",
            is_transfer=False,
        )

        # 승인됨 섹션 확인
        approval_section = blocks[-1]
        assert "✅" in approval_section["text"]["text"]
        assert "승인됨" in approval_section["text"]["text"]
        assert "박승인자" in approval_section["text"]["text"]

    def test_버튼이_없다(self):
        blocks = build_minimal_approved_message(
            requester_name="홍길동",
            thread_url="https://slack.com/test",
            approver_name="김승인",
            is_transfer=False,
        )

        assert all(block["type"] != "actions" for block in blocks)

    def test_업체이관_승인_완료_메시지(self):
        blocks = build_minimal_approved_message(
            requester_name="홍길동",
            thread_url="https://slack.com/test",
            approver_name="김승인",
            is_transfer=True,
        )

        header_section = blocks[0]
        assert "~*업체 이관 승인 요청*~" in header_section["text"]["text"]


class TestMinimalRejectedMessage:
    """승인 채널 반려 완료 메시지 테스트"""

    def test_반려_완료_메시지에_취소선이_적용된다(self):
        blocks = build_minimal_rejected_message(
            requester_name="홍길동",
            thread_url="https://slack.com/test",
            rejecter_name="김반려",
            is_transfer=False,
        )

        # 첫 번째 섹션에 취소선 (mrkdwn ~text~)
        header_section = blocks[0]
        assert header_section["text"]["type"] == "mrkdwn"
        assert "~*정산 이슈 승인 요청*~" in header_section["text"]["text"]

    def test_반려자_이름이_표시된다(self):
        blocks = build_minimal_rejected_message(
            requester_name="홍길동",
            thread_url="https://slack.com/test",
            rejecter_name="박반려자",
            is_transfer=False,
        )

        # 반려됨 섹션 확인
        rejection_section = blocks[-1]
        assert "❌" in rejection_section["text"]["text"]
        assert "반려됨" in rejection_section["text"]["text"]
        assert "박반려자" in rejection_section["text"]["text"]

    def test_버튼이_없다(self):
        blocks = build_minimal_rejected_message(
            requester_name="홍길동",
            thread_url="https://slack.com/test",
            rejecter_name="김반려",
            is_transfer=False,
        )

        assert all(block["type"] != "actions" for block in blocks)

    def test_업체이관_반려_완료_메시지(self):
        blocks = build_minimal_rejected_message(
            requester_name="홍길동",
            thread_url="https://slack.com/test",
            rejecter_name="김반려",
            is_transfer=True,
        )

        header_section = blocks[0]
        assert "~*업체 이관 승인 요청*~" in header_section["text"]["text"]


class TestApprovalRequestMessageIncludeButtons:
    """include_buttons 파라미터 테스트"""

    def test_include_buttons_false일때_버튼이_없다(self):
        data = _make_data(settlement_cost=10000, description="내용")
        blocks = build_approval_request_message(
            data, button_data="{}", include_buttons=False
        )

        assert all(block["type"] != "actions" for block in blocks)

    def test_include_buttons_true일때_버튼이_있다(self):
        data = _make_data(settlement_cost=10000, description="내용")
        blocks = build_approval_request_message(
            data, button_data="{}", include_buttons=True
        )

        assert blocks[-1]["type"] == "actions"
        assert len(blocks[-1]["elements"]) == 2


class TestMinimalProcessingMessage:
    """처리 중 표시 메시지 테스트"""

    def test_정산이슈_처리중_메시지(self):
        blocks = build_minimal_processing_message(is_transfer=False)

        assert blocks[0]["text"]["text"] == "정산 이슈 승인 요청"
        assert "처리 중" in blocks[1]["text"]["text"]

    def test_업체이관_처리중_메시지(self):
        blocks = build_minimal_processing_message(is_transfer=True)

        assert blocks[0]["text"]["text"] == "업체 이관 승인 요청"
        assert "처리 중" in blocks[1]["text"]["text"]

    def test_버튼이_없다(self):
        blocks = build_minimal_processing_message()

        assert all(block["type"] != "actions" for block in blocks)

    def test_블록_구조는_header와_section만_포함한다(self):
        blocks = build_minimal_processing_message()

        assert len(blocks) == 2
        assert blocks[0]["type"] == "header"
        assert blocks[1]["type"] == "section"


class TestTransferParsingResultMessage:
    """이관 예약 파싱 결과 메시지 빌더 테스트"""

    _COMMON_KWARGS = {
        "booking_key": "BK-001",
        "customer_name": "홍길동",
        "company_name": "업체A",
        "company_sub_name": "대리점B",
        "settlement_cost": "100000",
        "carmore_cost": "5000",
        "button_value": "{}",
    }

    def test_기본_호출시_context_블록_없음(self):
        blocks = build_transfer_parsing_result_message(**self._COMMON_KWARGS)

        context_blocks = [b for b in blocks if b["type"] == "context"]
        assert len(context_blocks) == 0

    def test_transfer_message_url_있으면_context_블록_추가(self):
        blocks = build_transfer_parsing_result_message(
            **self._COMMON_KWARGS,
            transfer_message_url="https://slack.com/archives/C123/p456",
        )

        context_blocks = [b for b in blocks if b["type"] == "context"]
        assert len(context_blocks) == 1
        assert "이관 예약 메시지 바로가기" in context_blocks[0]["elements"][0]["text"]
        assert (
            "https://slack.com/archives/C123/p456"
            in (context_blocks[0]["elements"][0]["text"])
        )

    def test_actions_블록은_항상_마지막(self):
        blocks = build_transfer_parsing_result_message(
            **self._COMMON_KWARGS,
            transfer_message_url="https://slack.com/test",
        )

        assert blocks[-1]["type"] == "actions"

    def test_빈_url은_context_블록_추가_안함(self):
        blocks = build_transfer_parsing_result_message(
            **self._COMMON_KWARGS,
            transfer_message_url="",
        )

        context_blocks = [b for b in blocks if b["type"] == "context"]
        assert len(context_blocks) == 0
