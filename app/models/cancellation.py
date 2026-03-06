from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SurveySubmission:
    """Jotform 설문 응답 1건."""

    submission_id: str
    customer_name: str  # 운전자 성함
    booking_key: str  # 예약번호
    submission_date: str = ""  # 접수일
    company_name: str = ""  # 업체명
    phone: str = ""  # 연락처
    image_url: str = ""  # Jotform 결항확인서 업로드 URL
    note: str = ""  # 추가 상담 내용

    @property
    def folder_name(self) -> str:
        """Google Drive 폴더명: 성함_예약번호."""
        return f"{self.customer_name}_{self.booking_key}"
