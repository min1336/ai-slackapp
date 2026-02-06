from __future__ import annotations

from dataclasses import dataclass, field

from app.core import get_logger
from app.exceptions import SpreadsheetError

logger = get_logger(__name__)


@dataclass(frozen=True)
class ColumnMapping:
    """헤더 해석 결과 (불변)."""

    field_to_index: dict[str, int] = field(default_factory=dict)

    def index_of(self, field_name: str) -> int:
        """0-based 인덱스 반환."""
        return self.field_to_index[field_name]

    def column_of(self, field_name: str) -> int:
        """1-based 컬럼 번호 반환 (gspread API용)."""
        return self.field_to_index[field_name] + 1

    def dict_to_row(
        self,
        data: dict[str, str],
        extra: dict[str, str] | None = None,
    ) -> list[str]:
        """dict를 시트 행(list)으로 변환."""
        merged = data | extra if extra else data
        max_col = max(self.field_to_index.values()) + 1
        row = [""] * max_col
        for field_name, idx in self.field_to_index.items():
            row[idx] = merged.get(field_name, "")
        return row

    def row_to_dict(self, values: list[str]) -> dict[str, str]:
        """시트 행(list)을 dict로 변환."""
        result: dict[str, str] = {}
        for field_name, idx in self.field_to_index.items():
            result[field_name] = values[idx] if idx < len(values) else ""
        return result


class ColumnMapper:
    """헤더 기반 동적 컬럼 해석기."""

    def __init__(self, field_to_header: dict[str, str]) -> None:
        self._field_to_header = field_to_header

    def resolve(
        self,
        actual_headers: list[str],
        required_fields: tuple[str, ...],
    ) -> ColumnMapping:
        """시트 헤더 행으로부터 필드별 인덱스를 해석한다.

        Args:
            actual_headers: 시트 1행의 헤더 값 리스트
            required_fields: 반드시 존재해야 하는 필드명 튜플

        Returns:
            해석된 ColumnMapping

        Raises:
            SpreadsheetError: 필수 헤더 누락 시
        """
        header_to_index = {h.strip(): i for i, h in enumerate(actual_headers)}

        field_to_index: dict[str, int] = {}
        missing: list[str] = []
        configured_headers: set[str] = set()

        for field_name in required_fields:
            header_name = self._field_to_header.get(field_name)
            if not header_name:
                missing.append(f"{field_name}(config_missing)")
                continue

            normalized_header = header_name.strip()
            configured_headers.add(normalized_header)
            idx = header_to_index.get(normalized_header)
            if idx is not None:
                field_to_index[field_name] = idx
            else:
                missing.append(f"{field_name}({header_name})")

        for field_name, header_name in self._field_to_header.items():
            if field_name in field_to_index:
                continue
            normalized_header = header_name.strip()
            configured_headers.add(normalized_header)
            idx = header_to_index.get(normalized_header)
            if idx is not None:
                field_to_index[field_name] = idx

        if missing:
            raise SpreadsheetError(
                message=("필수 헤더 누락: " + ", ".join(missing)),
                details={"missing": missing},
            )

        unmapped = {
            header.strip()
            for header in actual_headers
            if header.strip() and header.strip() not in configured_headers
        }
        if unmapped:
            logger.debug(
                "unmapped_headers_found",
                unmapped=sorted(unmapped),
            )

        return ColumnMapping(field_to_index=field_to_index)
