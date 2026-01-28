from __future__ import annotations

import json

from slack_bolt import App

from app.config import settings
from app.services.spreadsheet import SettlementRow, append_settlement_row
from app.views.options import (
    ISSUE_TYPE_OPTIONS,
    SELLER_CHANNEL_OPTIONS,
    DESCRIPTION_OPTIONS,
    find_option_by_text,
)


def register_action_handlers(app: App) -> None:

    @app.action("open_registration_modal")
    def handle_open_registration_modal(ack, body, client):
        ack()

        value = body.get("actions", [{}])[0].get("value", "{}")
        parsed = json.loads(value)

        booking_key = parsed.get("booking_key", "")
        company_name = parsed.get("company_name", "")
        customer_name = parsed.get("customer_name", "")

        user_id = body["user"]["id"]
        user_info = client.users_info(user=user_id)
        user_name = user_info["user"]["real_name"]

        channel_id = body.get("channel", {}).get("id", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")

        metadata = json.dumps({
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "user_name": user_name,
            "booking_key": booking_key,
            "company_name": company_name,
            "customer_name": customer_name,
        }, ensure_ascii=False)

        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "registration_submit",
                "private_metadata": metadata,
                "title": {"type": "plain_text", "text": "정산 이슈 등록"},
                "submit": {"type": "plain_text", "text": "등록"},
                "close": {"type": "plain_text", "text": "취소"},
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "📋 예약 정보"},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": "*정산 이슈 등록자*"},
                            {"type": "plain_text", "text": user_name},
                            {"type": "mrkdwn", "text": "*예약번호*"},
                            {"type": "plain_text", "text": booking_key or "(없음)"},
                            {"type": "mrkdwn", "text": "*업체명*"},
                            {"type": "plain_text", "text": company_name or "(없음)"},
                            {"type": "mrkdwn", "text": "*고객명*"},
                            {"type": "plain_text", "text": customer_name or "(없음)"},
                        ],
                    },
                    {"type": "divider"},
                    {
                        "type": "input",
                        "block_id": "settlement_standard_day_block",
                        "label": {"type": "plain_text", "text": "정산기준일 (필수)"},
                        "element": {
                            "type": "datepicker",
                            "action_id": "settlement_standard_day_input",
                            "placeholder": {"type": "plain_text", "text": "날짜 선택"},
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "issue_type_block",
                        "label": {"type": "plain_text", "text": "이슈사항 (필수)"},
                        "element": {
                            "type": "static_select",
                            "action_id": "issue_type_input",
                            "placeholder": {"type": "plain_text", "text": "선택하세요"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "정산제외"}, "value": "ignore_settlement"},
                                {"text": {"type": "plain_text", "text": "취소수수료"}, "value": "cancel_charge_fee"},
                                {"text": {"type": "plain_text", "text": "금액변경"}, "value": "cost_changed"},
                                {"text": {"type": "plain_text", "text": "대신배차"}, "value": "instead_dispatch"},
                                {"text": {"type": "plain_text", "text": "정산추가"}, "value": "add_settlement"},
                                {"text": {"type": "plain_text", "text": "조기반납(전)"}, "value": "early_return_before"},
                                {"text": {"type": "plain_text", "text": "조기반납(후)"}, "value": "early_return_after"},
                                {"text": {"type": "plain_text", "text": "기타"}, "value": "etc"},
                            ],
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "company_sub_name_block",
                        "label": {"type": "plain_text", "text": "업체명2(대신배차)"},
                        "optional": True,
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "company_sub_name_input",
                            "initial_value": "",
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "settlement_standard_cost_block",
                        "label": {"type": "plain_text", "text": "정산기준금액 (필수)"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "settlement_standard_cost_input",
                            "initial_value": "",
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "carmore_cost_block",
                        "label": {"type": "plain_text", "text": "카모아 부담비용"},
                        "optional": True,
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "carmore_cost_input",
                            "initial_value": "",
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "user_refund_cost_block",
                        "label": {"type": "plain_text", "text": "고객 환불 금액"},
                        "optional": True,
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "user_refund_cost_input",
                            "initial_value": "",
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "seller_channel_block",
                        "label": {"type": "plain_text", "text": "판매채널 (필수)"},
                        "element": {
                            "type": "static_select",
                            "action_id": "seller_channel_input",
                            "placeholder": {"type": "plain_text", "text": "선택하세요"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "카모아"}, "value": "carmore"},
                                {"text": {"type": "plain_text", "text": "티맵"}, "value": "tmap"},
                                {"text": {"type": "plain_text", "text": "클룩"}, "value": "klook"},
                                {"text": {"type": "plain_text", "text": "웹투어"}, "value": "web_tour"},
                                {"text": {"type": "plain_text", "text": "야놀자"}, "value": "yanolja"},
                                {"text": {"type": "plain_text", "text": "인바운드"}, "value": "inbound"},
                                {"text": {"type": "plain_text", "text": "트레블버킷"}, "value": "travel_bucket"},
                                {"text": {"type": "plain_text", "text": "루아"}, "value": "lua"},
                                {"text": {"type": "plain_text", "text": "비즈플레이"}, "value": "biz_play"},
                                {"text": {"type": "plain_text", "text": "트립닷컴"}, "value": "trip_dot_com"},
                            ],
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "description_block",
                        "label": {"type": "plain_text", "text": "내용 (필수)"},
                        "element": {
                            "type": "static_select",
                            "action_id": "description_input",
                            "placeholder": {"type": "plain_text", "text": "선택하세요"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "배차불가로 인한 정산제외 (정산 100% 제외)"}, "value": "exclude_unable_dispatch"},
                                {"text": {"type": "plain_text", "text": "결항으로 인한 정산제외 (정산 100% 제외)"}, "value": "exclude_flight_cancel"},
                                {"text": {"type": "plain_text", "text": "파트너사 협의 후 정산제외 (정산 100% 제외)"}, "value": "exclude_partner"},
                                {"text": {"type": "plain_text", "text": "실 사용기간 변경으로 정산기준일 변동"}, "value": "change_usage_period"},
                                {"text": {"type": "plain_text", "text": "배차불가로 인한 이관"}, "value": "transfer_unable_dispatch"},
                                {"text": {"type": "plain_text", "text": "예약변경으로 인한 이관"}, "value": "transfer_reservation"},
                                {"text": {"type": "plain_text", "text": "결항으로 인한 부분환불"}, "value": "partial_flight_cancel"},
                                {"text": {"type": "plain_text", "text": "파트너사 협의 후 부분환불"}, "value": "partial_partner"},
                                {"text": {"type": "plain_text", "text": "파트너사 협의 후 5% 공제 후 환불"}, "value": "refund_partner_5"},
                                {"text": {"type": "plain_text", "text": "파트너사 협의 후 10% 공제 후 환불"}, "value": "refund_partner_10"},
                                {"text": {"type": "plain_text", "text": "파트너사 협의 후 10% 공제 후 환불"}, "value": "refund_partner_10_2"},
                                {"text": {"type": "plain_text", "text": "파트너사 협의 후 20% 공제 후 환불"}, "value": "refund_partner_20"},
                                {"text": {"type": "plain_text", "text": "파트너사 협의 후 30% 공제 후 환불"}, "value": "refund_partner_30"},
                                {"text": {"type": "plain_text", "text": "대여조건 미달로 50% 공제 후 환불"}, "value": "refund_condition_50"},
                                {"text": {"type": "plain_text", "text": "대여조건 미달로 30% 공제 후 환불"}, "value": "refund_condition_30"},
                                {"text": {"type": "plain_text", "text": "실 사용기간 변경으로 정산기준일 변동"}, "value": "change_usage_period_2"},
                                {"text": {"type": "plain_text", "text": "월렌트 반납일 이후 연장(정산일 변동)"}, "value": "monthly_extend"},
                                {"text": {"type": "plain_text", "text": "조기반납으로 인한 정산기준금 변동"}, "value": "early_return"},
                                {"text": {"type": "plain_text", "text": "오매칭으로 인한 정산추가"}, "value": "add_mismatch"},
                                {"text": {"type": "plain_text", "text": "정산누락으로 추가필요"}, "value": "add_missing"},
                                {"text": {"type": "plain_text", "text": "중복 정산되어 다음정산에서 차감필요"}, "value": "deduct_duplicate"},
                                {"text": {"type": "plain_text", "text": "정산 후 환불 (파트너사 협의 후 다음 정산에서 차감)"}, "value": "refund_after_settlement"},
                                {"text": {"type": "plain_text", "text": "카드결제전 오류로 확인됐지만 취소로 인한 정산제외"}, "value": "exclude_card_error"},
                                {"text": {"type": "plain_text", "text": "정상예약건 / 카드결제전에서 확인 가능 (정산필요건)"}, "value": "normal_need_settlement"},
                                {"text": {"type": "plain_text", "text": "인바운드 (정산기준금액 그대로 정산 필요)"}, "value": "inbound_as_is"},
                                {"text": {"type": "plain_text", "text": "api 통신오류 건 수기 취소 (전액환불 구간)"}, "value": "api_error_cancel"},
                                {"text": {"type": "plain_text", "text": "월구독 수기결제 진행 된 건 정산 누락 방지 차 기재"}, "value": "monthly_sub_manual"},
                            ],
                        },
                    },
                ],
            },
        )

    @app.action("settlement_approve")
    def handle_settlement_approve(ack, body, client):
        ack()

        user_id = body["user"]["id"]
        channel_id = body.get("channel", {}).get("id", "")
        message_ts = body.get("message", {}).get("ts", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")

        if user_id not in settings.approver_ids:
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="⚠️ 승인 권한이 없습니다.",
                thread_ts=thread_ts if thread_ts else None,
            )
            return

        user_info = client.users_info(user=user_id)
        approver_name = user_info["user"]["real_name"]

        # 버튼 value에서 데이터 추출
        value = body.get("actions", [{}])[0].get("value", "{}")
        data = json.loads(value)

        # 스프레드시트에 저장
        row = SettlementRow(
            settlement_day=data.get("settlement_day", ""),
            user_name=data.get("user_name", ""),
            customer_name=data.get("customer_name", ""),
            booking_key=data.get("booking_key", ""),
            company_name=data.get("company_name", ""),
            company_sub_name=data.get("company_sub_name", ""),
            settlement_cost=data.get("settlement_cost", ""),
            carmore_cost=data.get("carmore_cost", ""),
            user_refund_cost=data.get("user_refund_cost", ""),
            issue_type=data.get("issue_type", ""),
            sales_channel=data.get("seller_channel", ""),
            description=data.get("description", ""),
            status="승인",
            approver_name=approver_name,
        )
        append_settlement_row(row)

        # 메시지 업데이트
        original_blocks = body.get("message", {}).get("blocks", [])

        new_blocks = [b for b in original_blocks if b.get("type") != "actions"]
        new_blocks[0] = {
            "type": "header",
            "text": {"type": "plain_text", "text": "✅ 정산 이슈가 승인되었습니다."},
        }
        new_blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"승인자: *{approver_name}*"}
            ],
        })

        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text="정산 이슈 승인됨",
            blocks=new_blocks,
        )

    @app.action("settlement_reject")
    def handle_settlement_reject(ack, body, client):
        ack()

        user_id = body["user"]["id"]
        channel_id = body.get("channel", {}).get("id", "")
        message_ts = body.get("message", {}).get("ts", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")

        if user_id not in settings.approver_ids:
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="⚠️ 반려 권한이 없습니다.",
                thread_ts=thread_ts if thread_ts else None,
            )
            return

        user_info = client.users_info(user=user_id)
        rejecter_name = user_info["user"]["real_name"]

        # 버튼 value에서 데이터 추출
        value = body.get("actions", [{}])[0].get("value", "{}")
        data = json.loads(value)

        # 스프레드시트에 저장
        row = SettlementRow(
            settlement_day=data.get("settlement_day", ""),
            user_name=data.get("user_name", ""),
            customer_name=data.get("customer_name", ""),
            booking_key=data.get("booking_key", ""),
            company_name=data.get("company_name", ""),
            company_sub_name=data.get("company_sub_name", ""),
            settlement_cost=data.get("settlement_cost", ""),
            carmore_cost=data.get("carmore_cost", ""),
            user_refund_cost=data.get("user_refund_cost", ""),
            issue_type=data.get("issue_type", ""),
            sales_channel=data.get("seller_channel", ""),
            description=data.get("description", ""),
            status="반려",
            approver_name=rejecter_name,
        )
        append_settlement_row(row)

        # 메시지 업데이트
        original_blocks = body.get("message", {}).get("blocks", [])

        new_blocks = [b for b in original_blocks if b.get("type") != "actions"]
        new_blocks[0] = {
            "type": "header",
            "text": {"type": "plain_text", "text": "❌ 정산 이슈가 반려되었습니다."},
        }
        new_blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"반려자: *{rejecter_name}*"}
            ],
        })

        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text="정산 이슈 반려됨",
            blocks=new_blocks,
        )

    @app.action("settlement_edit")
    def handle_settlement_edit(ack, body, client):
        ack()

        # 버튼 value에서 기존 데이터 추출
        value = body.get("actions", [{}])[0].get("value", "{}")
        data = json.loads(value)

        channel_id = body.get("channel", {}).get("id", "")
        message_ts = body.get("message", {}).get("ts", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")

        user_name = data.get("user_name", "")
        booking_key = data.get("booking_key", "")
        company_name = data.get("company_name", "")
        customer_name = data.get("customer_name", "")

        # 기존 입력값
        settlement_day = data.get("settlement_day", "")
        issue_type = data.get("issue_type", "")
        company_sub_name = data.get("company_sub_name", "")
        settlement_cost = data.get("settlement_cost", "")
        carmore_cost = data.get("carmore_cost", "")
        user_refund_cost = data.get("user_refund_cost", "")
        seller_channel = data.get("seller_channel", "")
        description = data.get("description", "")

        metadata = json.dumps({
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "message_ts": message_ts,  # 편집 모드 표시
            "user_name": user_name,
            "booking_key": booking_key,
            "company_name": company_name,
            "customer_name": customer_name,
        }, ensure_ascii=False)

        # static_select initial_option 찾기
        issue_type_initial = find_option_by_text(ISSUE_TYPE_OPTIONS, issue_type)
        seller_channel_initial = find_option_by_text(SELLER_CHANNEL_OPTIONS, seller_channel)
        description_initial = find_option_by_text(DESCRIPTION_OPTIONS, description)

        # 모달 블록 구성
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📋 예약 정보"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": "*정산 이슈 등록자*"},
                    {"type": "plain_text", "text": user_name},
                    {"type": "mrkdwn", "text": "*예약번호*"},
                    {"type": "plain_text", "text": booking_key or "(없음)"},
                    {"type": "mrkdwn", "text": "*업체명*"},
                    {"type": "plain_text", "text": company_name or "(없음)"},
                    {"type": "mrkdwn", "text": "*고객명*"},
                    {"type": "plain_text", "text": customer_name or "(없음)"},
                ],
            },
            {"type": "divider"},
        ]

        # 정산기준일
        datepicker_element = {
            "type": "datepicker",
            "action_id": "settlement_standard_day_input",
            "placeholder": {"type": "plain_text", "text": "날짜 선택"},
        }
        if settlement_day:
            datepicker_element["initial_date"] = settlement_day
        blocks.append({
            "type": "input",
            "block_id": "settlement_standard_day_block",
            "label": {"type": "plain_text", "text": "정산기준일 (필수)"},
            "element": datepicker_element,
        })

        # 이슈사항
        issue_type_element = {
            "type": "static_select",
            "action_id": "issue_type_input",
            "placeholder": {"type": "plain_text", "text": "선택하세요"},
            "options": ISSUE_TYPE_OPTIONS,
        }
        if issue_type_initial:
            issue_type_element["initial_option"] = issue_type_initial
        blocks.append({
            "type": "input",
            "block_id": "issue_type_block",
            "label": {"type": "plain_text", "text": "이슈사항 (필수)"},
            "element": issue_type_element,
        })

        # 업체명2
        blocks.append({
            "type": "input",
            "block_id": "company_sub_name_block",
            "label": {"type": "plain_text", "text": "업체명2(대신배차)"},
            "optional": True,
            "element": {
                "type": "plain_text_input",
                "action_id": "company_sub_name_input",
                "initial_value": company_sub_name,
            },
        })

        # 정산기준금액
        blocks.append({
            "type": "input",
            "block_id": "settlement_standard_cost_block",
            "label": {"type": "plain_text", "text": "정산기준금액 (필수)"},
            "element": {
                "type": "plain_text_input",
                "action_id": "settlement_standard_cost_input",
                "initial_value": settlement_cost,
            },
        })

        # 카모아 부담비용
        blocks.append({
            "type": "input",
            "block_id": "carmore_cost_block",
            "label": {"type": "plain_text", "text": "카모아 부담비용"},
            "optional": True,
            "element": {
                "type": "plain_text_input",
                "action_id": "carmore_cost_input",
                "initial_value": carmore_cost,
            },
        })

        # 고객 환불 금액
        blocks.append({
            "type": "input",
            "block_id": "user_refund_cost_block",
            "label": {"type": "plain_text", "text": "고객 환불 금액"},
            "optional": True,
            "element": {
                "type": "plain_text_input",
                "action_id": "user_refund_cost_input",
                "initial_value": user_refund_cost,
            },
        })

        # 판매채널
        seller_channel_element = {
            "type": "static_select",
            "action_id": "seller_channel_input",
            "placeholder": {"type": "plain_text", "text": "선택하세요"},
            "options": SELLER_CHANNEL_OPTIONS,
        }
        if seller_channel_initial:
            seller_channel_element["initial_option"] = seller_channel_initial
        blocks.append({
            "type": "input",
            "block_id": "seller_channel_block",
            "label": {"type": "plain_text", "text": "판매채널 (필수)"},
            "element": seller_channel_element,
        })

        # 내용
        description_element = {
            "type": "static_select",
            "action_id": "description_input",
            "placeholder": {"type": "plain_text", "text": "선택하세요"},
            "options": DESCRIPTION_OPTIONS,
        }
        if description_initial:
            description_element["initial_option"] = description_initial
        blocks.append({
            "type": "input",
            "block_id": "description_block",
            "label": {"type": "plain_text", "text": "내용 (필수)"},
            "element": description_element,
        })

        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "registration_submit",
                "private_metadata": metadata,
                "title": {"type": "plain_text", "text": "정산 이슈 편집"},
                "submit": {"type": "plain_text", "text": "수정"},
                "close": {"type": "plain_text", "text": "취소"},
                "blocks": blocks,
            },
        )
