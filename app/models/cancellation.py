from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SurveySubmission:
    """Jotform 설문 응답 1건."""

    submission_id: str
    customer_name: str  # 운전자 성함
    booking_key: str  # 예약번호 (정규화됨)
    submission_date: str = ""  # 접수일
    company_name: str = ""  # 업체명
    phone: str = ""  # 연락처
    image_url: str = ""  # Jotform 결항확인서 업로드 URL
    note: str = ""  # 추가 상담 내용

    @property
    def folder_name(self) -> str:
        """Google Drive 폴더명: 성함_예약번호_제출날짜."""
        date_str = self.submission_date
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
        return f"{self.customer_name}_{self.booking_key}_{date_str}"


@dataclass
class ReservationData:
    """예약 채널에서 수집한 예약 정보."""

    booking_key: str = ""
    customer_name: str = ""
    phone: str = ""
    rental_period_start: datetime | None = None
    rental_period_end: datetime | None = None
    company_name: str = ""
    payment_amount: int | None = None


@dataclass
class DriveFile:
    """Google Drive 파일 메타데이터."""

    id: str
    name: str
    mime_type: str
