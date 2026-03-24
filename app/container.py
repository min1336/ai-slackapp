from __future__ import annotations

from typing import TYPE_CHECKING

import gspread
from google.oauth2.service_account import Credentials

from app.config import (
    get_app_config,
    get_gemini_settings,
    get_openai_settings,
    get_spreadsheet_settings,
)
from app.core import get_logger
from app.infrastructure.database import SessionFactory, get_session
from app.infrastructure.drive_client import DriveImageClient
from app.infrastructure.fallback_gateway import FallbackImageGateway
from app.infrastructure.gemini_client import GeminiClient
from app.infrastructure.openai_client import OpenAIImageClient
from app.infrastructure.spreadsheet import SCOPES, SpreadsheetService
from app.infrastructure.survey_sheet import SurveySheetReader
from app.services.approval_service import ApprovalService
from app.services.cancellation_image_service import CancellationImageService
from app.services.drive_file_collector import DriveFileCollector
from app.services.image_analyzer import ImageAnalyzer
from app.services.pdf_converter import PdfConverter
from app.services.rejection_service import RejectionService
from app.services.reservation_locator import ReservationLocator
from app.services.settlement_registration_service import (
    SettlementRegistrationService,
)
from app.services.settlement_writer import SettlementWriter
from app.services.slack_reader import SlackReader
from app.services.slack_writer import SlackWriter
from app.services.sync_processor import SyncProcessor
from app.services.sync_service import SyncService
from app.services.thread_discovery_service import ThreadDiscoveryService
from app.services.thread_reference_store import ThreadReferenceStore
from app.services.transfer_lifecycle_service import TransferLifecycleService

logger = get_logger(__name__)

if TYPE_CHECKING:
    from slack_sdk import WebClient

    from app.infrastructure.protocols import SpreadsheetGateway


class ServiceContainer:
    """DI 와이어링 — 모든 서비스 인스턴스를 생성한다.

    테스트에서는 get_session/sheets를 교체하여 전체 서비스 그래프를 Fake로 전환.
    """

    def __init__(
        self,
        client: WebClient,
        get_session_fn: SessionFactory = get_session,
        sheets: SpreadsheetGateway | None = None,
    ) -> None:
        config = get_app_config()
        spreadsheet_settings = get_spreadsheet_settings()

        if sheets is None:

            def _create_spreadsheet_client() -> gspread.Spreadsheet:
                credentials = Credentials.from_service_account_file(
                    spreadsheet_settings.credentials_file,
                    scopes=SCOPES,
                )
                gc = gspread.authorize(credentials)
                return gc.open_by_key(config.settlement.spreadsheet.id)

            _sheets: SpreadsheetGateway = SpreadsheetService(
                client_factory=_create_spreadsheet_client,
                sheet_name_resolver=config.settlement.spreadsheet.sheet_name,
                field_to_header_resolver=config.settlement.spreadsheet.field_to_header,
                header_row_resolver=config.settlement.spreadsheet.header_row,
            )
        else:
            _sheets = sheets

        approvers = frozenset(config.settlement.approvers)

        # Components
        self.reader = SlackReader(client)
        self.writer = SlackWriter(client)

        approval_channel = config.settlement.approval_channel_id
        writer = self.writer

        def _on_sync_failed(booking_key: str, error: str) -> None:
            writer.post_message(
                channel=approval_channel,
                text=f"⚠️ 시트 동기화 실패: {booking_key}\n에러: {error}",
            )

        self.sync_processor = SyncProcessor(
            get_session_fn, _sheets, on_sync_failed=_on_sync_failed
        )
        self.settlement_writer = SettlementWriter(get_session_fn, self.sync_processor)
        self.thread_ref_store = ThreadReferenceStore(get_session_fn)

        self.transfer_lifecycle = TransferLifecycleService(
            get_session_fn, self.thread_ref_store, _sheets
        )

        # Orchestrators
        self.approval = ApprovalService(
            self.reader,
            self.writer,
            self.settlement_writer,
            approvers,
            sheets=_sheets,
        )
        self.rejection = RejectionService(
            self.reader,
            self.writer,
            self.settlement_writer,
            approvers,
            sheets=_sheets,
            transfer_lifecycle=self.transfer_lifecycle,
        )
        self.registration = SettlementRegistrationService(
            self.reader,
            self.writer,
            self.settlement_writer,
            approval_channel_id=config.settlement.approval_channel_id,
            transfer_lifecycle=self.transfer_lifecycle,
        )
        self.discovery = ThreadDiscoveryService(
            self.thread_ref_store,
            self.reader,
            reservation_channels=config.settlement.slack_channels.reservation,
        )
        self.sync_service = SyncService(self.sync_processor, _sheets)

        # Channels (listener에서 참조)
        self.reservation_channels = config.settlement.slack_channels.reservation
        self.transfer_channel = config.settlement.slack_channels.transfer_reservation

        # Cancellation — 설정이 있을 때만 와이어링
        cancel_cfg = config.cancellation
        cancel_target = cancel_cfg.slack_channels.target
        cancel_sheet_id = cancel_cfg.spreadsheet.id
        cancel_drive_id = cancel_cfg.drive.parent_folder_id

        if cancel_target and cancel_drive_id and cancel_sheet_id:

            def _create_cancel_spreadsheet() -> gspread.Spreadsheet:
                credentials = Credentials.from_service_account_file(
                    spreadsheet_settings.credentials_file,
                    scopes=SCOPES,
                )
                gc = gspread.authorize(credentials)
                return gc.open_by_key(cancel_sheet_id)

            _survey = SurveySheetReader(
                client_factory=_create_cancel_spreadsheet,
                sheet_name=cancel_cfg.spreadsheet.survey_sheet_name,
                formatted_sheet_name=cancel_cfg.spreadsheet.formatted_sheet_name,
            )
            _drive = DriveImageClient(
                credentials_file=spreadsheet_settings.credentials_file,
                parent_folder_id=cancel_drive_id,
            )
            # Image analysis (feature flag)
            _analyzer = None
            _gateway = None
            if cancel_cfg.analysis.enabled:
                gemini_settings = get_gemini_settings()
                openai_settings = get_openai_settings()
                if gemini_settings.api_key:
                    _gateway = GeminiClient(
                        api_key=gemini_settings.api_key,
                        model=cancel_cfg.analysis.gemini_model,
                        timeout=cancel_cfg.analysis.timeout_seconds,
                    )
                    if openai_settings.api_key:
                        _fallback = OpenAIImageClient(
                            api_key=openai_settings.api_key,
                            model=cancel_cfg.analysis.openai_model,
                            timeout=cancel_cfg.analysis.timeout_seconds,
                        )
                        _gateway = FallbackImageGateway(  # type: ignore[assignment]
                            primary=_gateway,
                            fallback=_fallback,
                        )
                elif openai_settings.api_key:
                    _gateway = OpenAIImageClient(
                        api_key=openai_settings.api_key,
                        model=cancel_cfg.analysis.openai_model,
                        timeout=cancel_cfg.analysis.timeout_seconds,
                    )
                if _gateway:
                    _analyzer = ImageAnalyzer(_gateway)

            if _analyzer:
                logger.info(
                    "cancellation_analyzer_ready",
                    model=cancel_cfg.analysis.gemini_model,
                    gateway_type=type(_gateway).__name__,
                )
            elif not cancel_cfg.analysis.enabled:
                logger.info(
                    "cancellation_analyzer_disabled",
                    reason="analysis.enabled=false",
                )
            else:
                logger.warning(
                    "cancellation_analyzer_disabled",
                    reason="no_api_key",
                    analysis_enabled=True,
                )

            _collector = DriveFileCollector(drive=_drive, pdf_converter=PdfConverter())
            _reservation_locator = ReservationLocator(
                reader=self.reader,
                reservation_channels=config.settlement.slack_channels.reservation,
                thread_ref_store=self.thread_ref_store,
                exclude_text="예약취소",
            )

            self.cancellation_image = CancellationImageService(
                survey_sheet=_survey,
                file_collector=_collector,
                writer=self.writer,
                reader=self.reader,
                target_channel=cancel_target,
                analyzer=_analyzer,
                reservation_locator=_reservation_locator,
                overseas_prefixes=cancel_cfg.overseas.prefixes,
                overseas_mention=cancel_cfg.overseas.mention,
                overseas_reaction=cancel_cfg.overseas.reaction,
            )
        else:
            self.cancellation_image = None  # type: ignore[assignment]

        self.cancellation_target_channel = cancel_target
