from __future__ import annotations

from app.services.jotform_parser import parse_jotform_answers


class TestParseJotformAnswers:
    def test_정상_페이로드_파싱(self):
        content = {
            "created_at": "2026-03-06 02:12:08",
            "answers": {
                "12": {"answer": "홍길동"},
                "14": {"answer": "R12345"},
                "26": {"answer": "렌트카A"},
                "13": {"answer": {"full": "010-1234-5678"}},
                "11": {
                    "answer": [
                        "https://jotform.com/uploads/file.pdf",
                        "https://jotform.com/uploads/image.png",
                    ]
                },
                "17": {"answer": "추가 메모"},
            },
        }
        sub, file_urls = parse_jotform_answers(
            submission_id="99001",
            content=content,
        )
        assert sub.submission_id == "99001"
        assert sub.customer_name == "홍길동"
        assert sub.booking_key == "R12345"
        assert sub.company_name == "렌트카A"
        assert sub.phone == "010-1234-5678"
        assert sub.note == "추가 메모"
        assert sub.submission_date == "2026-03-06 02:12:08"
        assert file_urls == [
            "https://jotform.com/uploads/file.pdf",
            "https://jotform.com/uploads/image.png",
        ]

    def test_선택_필드_비어있어도_파싱(self):
        content = {
            "answers": {
                "12": {"answer": "김철수"},
                "14": {"answer": "WB999"},
                "26": {"answer": ""},
                "13": {"answer": {"full": ""}},
                "11": {"answer": ["https://jotform.com/uploads/a.jpg"]},
            },
        }
        sub, file_urls = parse_jotform_answers(
            submission_id="99002",
            content=content,
        )
        assert sub.customer_name == "김철수"
        assert sub.booking_key == "WB999"
        assert sub.company_name == ""
        assert sub.phone == ""
        assert sub.note == ""
        assert sub.submission_date == ""
        assert len(file_urls) == 1

    def test_파일_없으면_빈_리스트(self):
        content = {
            "answers": {
                "12": {"answer": "테스트"},
                "14": {"answer": "AB111"},
                "26": {"answer": ""},
                "13": {"answer": {"full": ""}},
                "11": {},
            },
        }
        _, file_urls = parse_jotform_answers(
            submission_id="99003",
            content=content,
        )
        assert file_urls == []
