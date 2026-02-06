from __future__ import annotations

import pytest

from app.exceptions import SpreadsheetError
from app.infrastructure.column_mapper import ColumnMapper, ColumnMapping

SAMPLE_FIELD_TO_HEADER = {
    "settlement_day": "정산기준일",
    "user_name": "작성자",
    "booking_key": "예약번호",
    "status": "처리",
}

REQUIRED = ("settlement_day", "user_name", "booking_key", "status")


class TestColumnMapping:
    """ColumnMapping 단위 테스트"""

    def test_index_of_0based(self):
        mapping = ColumnMapping(field_to_index={"booking_key": 2, "status": 5})
        assert mapping.index_of("booking_key") == 2
        assert mapping.index_of("status") == 5

    def test_column_of_1based(self):
        mapping = ColumnMapping(field_to_index={"booking_key": 2})
        assert mapping.column_of("booking_key") == 3

    def test_dict_to_row_기본(self):
        mapping = ColumnMapping(field_to_index={"a": 0, "b": 1, "c": 2})
        row = mapping.dict_to_row({"a": "1", "b": "2", "c": "3"})
        assert row == ["1", "2", "3"]

    def test_dict_to_row_extra(self):
        mapping = ColumnMapping(field_to_index={"a": 0, "b": 1, "extra": 2})
        row = mapping.dict_to_row({"a": "1", "b": "2"}, extra={"extra": "X"})
        assert row == ["1", "2", "X"]

    def test_dict_to_row_컬럼_재배치(self):
        mapping = ColumnMapping(field_to_index={"a": 2, "b": 0, "c": 1})
        row = mapping.dict_to_row({"a": "A", "b": "B", "c": "C"})
        assert row == ["B", "C", "A"]

    def test_row_to_dict_기본(self):
        mapping = ColumnMapping(field_to_index={"a": 0, "b": 1, "c": 2})
        result = mapping.row_to_dict(["1", "2", "3"])
        assert result == {"a": "1", "b": "2", "c": "3"}

    def test_row_to_dict_짧은_행(self):
        mapping = ColumnMapping(field_to_index={"a": 0, "b": 1, "c": 5})
        result = mapping.row_to_dict(["X", "Y"])
        assert result == {"a": "X", "b": "Y", "c": ""}


class TestColumnMapper:
    """ColumnMapper 단위 테스트"""

    def test_정상_해석(self):
        mapper = ColumnMapper(SAMPLE_FIELD_TO_HEADER)
        headers = ["정산기준일", "작성자", "예약번호", "처리"]
        mapping = mapper.resolve(headers, REQUIRED)

        assert mapping.index_of("settlement_day") == 0
        assert mapping.index_of("user_name") == 1
        assert mapping.index_of("booking_key") == 2
        assert mapping.index_of("status") == 3

    def test_컬럼_재배치_대응(self):
        mapper = ColumnMapper(SAMPLE_FIELD_TO_HEADER)
        headers = ["처리", "예약번호", "작성자", "정산기준일"]
        mapping = mapper.resolve(headers, REQUIRED)

        assert mapping.index_of("status") == 0
        assert mapping.index_of("booking_key") == 1
        assert mapping.index_of("user_name") == 2
        assert mapping.index_of("settlement_day") == 3

    def test_필수_헤더_누락시_에러(self):
        mapper = ColumnMapper(SAMPLE_FIELD_TO_HEADER)
        headers = ["정산기준일", "작성자"]

        with pytest.raises(SpreadsheetError, match="필수 헤더 누락"):
            mapper.resolve(headers, REQUIRED)

    def test_필수_필드가_config에_없으면_에러(self):
        mapper = ColumnMapper(
            {
                "settlement_day": "정산기준일",
                "user_name": "작성자",
                "status": "처리",
            }
        )
        headers = ["정산기준일", "작성자", "예약번호", "처리"]

        with pytest.raises(SpreadsheetError, match="booking_key\\(config_missing\\)"):
            mapper.resolve(headers, REQUIRED)

    def test_추가_헤더는_무시(self):
        mapper = ColumnMapper(SAMPLE_FIELD_TO_HEADER)
        headers = ["정산기준일", "작성자", "예약번호", "처리", "미지정컬럼"]
        mapping = mapper.resolve(headers, REQUIRED)
        assert mapping.index_of("settlement_day") == 0

    def test_선택_필드_누락은_에러_아님(self):
        mapper = ColumnMapper({**SAMPLE_FIELD_TO_HEADER, "note": "비고"})
        headers = ["정산기준일", "작성자", "예약번호", "처리"]
        mapping = mapper.resolve(headers, REQUIRED)
        assert "note" not in mapping.field_to_index
