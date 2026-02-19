from __future__ import annotations

from typing import TYPE_CHECKING

import gspread
from google.oauth2.service_account import Credentials

from app.config import get_app_config, get_spreadsheet_settings
from app.infrastructure.database import SessionFactory, get_session
from app.infrastructure.spreadsheet import SCOPES, SpreadsheetService
from app.services.approval_service import ApprovalService
from app.services.rejection_service import RejectionService
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

        if sheets is None:
            spreadsheet_settings = get_spreadsheet_settings()

            def _create_spreadsheet_client() -> gspread.Spreadsheet:
                credentials = Credentials.from_service_account_file(
                    spreadsheet_settings.credentials_file,
                    scopes=SCOPES,
                )
                gc = gspread.authorize(credentials)
                return gc.open_by_key(config.spreadsheet.id)

            _sheets: SpreadsheetGateway = SpreadsheetService(
                client_factory=_create_spreadsheet_client,
                sheet_name_resolver=config.spreadsheet.sheet_name,
                field_to_header_resolver=config.spreadsheet.field_to_header,
            )
        else:
            _sheets = sheets

        approvers = frozenset(config.approvers)

        # Components
        self.reader = SlackReader(client)
        self.writer = SlackWriter(client)
        self.sync_processor = SyncProcessor(get_session_fn, _sheets)
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
            approval_channel_id=config.approval_channel_id,
            transfer_lifecycle=self.transfer_lifecycle,
        )
        self.discovery = ThreadDiscoveryService(
            self.thread_ref_store,
            self.reader,
            reservation_channel=config.slack_channels.reservation,
        )
        self.sync_service = SyncService(self.sync_processor, _sheets)

        # Channels (listener에서 참조)
        self.reservation_channel = config.slack_channels.reservation
        self.transfer_channel = config.slack_channels.transfer_reservation
