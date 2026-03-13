from __future__ import annotations

from datetime import datetime

from app.models.analysis import AnalysisResult, CrossVerificationResult
from app.models.cancellation import ReservationData, SurveySubmission
from app.services.cross_verifier import CrossVerifier
from tests.fakes.fake_gemini import FakeGeminiClient


def _analysis(
    document_type="항공사 운항정보확인서",
    fields=None,
    quality_issues=None,
) -> AnalysisResult:
    return AnalysisResult(
        document_type=document_type,
        extracted_fields=fields
        or {
            "고객명": "박성구",
            "예약번호": "OR2017576",
            "날짜": "2026-02-27",
            "항공편": "LJ473",
            "결항사유": "기상악화",
            "발급기관": "진에어",
        },
        summary="진에어 LJ473편 기상악화 결항.",
        quality_issues=quality_issues or [],
    )


def _reservation(
    booking_key="OR2017576",
    customer_name="박성구",
    phone="010-6680-0292",
    start=datetime(2026, 2, 27, 21, 0),
    end=datetime(2026, 3, 2, 19, 30),
    company_name="패밀리렌트카 본사 [제주]",
) -> ReservationData:
    return ReservationData(
        booking_key=booking_key,
        customer_name=customer_name,
        phone=phone,
        rental_period_start=start,
        rental_period_end=end,
        company_name=company_name,
    )


def _submission(
    booking_key="OR2017576",
    customer_name="박성구",
    phone="010-6680-0292",
) -> SurveySubmission:
    return SurveySubmission(
        submission_id="1001",
        customer_name=customer_name,
        booking_key=booking_key,
        phone=phone,
    )


def _get_comparison(result: CrossVerificationResult, field_name: str):
    for c in result.field_comparisons:
        if c.field_name == field_name:
            return c
    return None


class TestCompareFields:
    def test_고객명_완전일치(self):
        verifier = CrossVerifier()
        result = verifier.verify(_analysis(), _reservation(), _submission())
        comp = _get_comparison(result, "고객명")
        assert comp is not None
        assert comp.status == "일치"

    def test_고객명_포함관계_일치(self):
        verifier = CrossVerifier()
        analysis = _analysis(
            fields={
                "고객명": "박성",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            }
        )
        result = verifier.verify(
            analysis, _reservation(customer_name="박성구"), _submission()
        )
        comp = _get_comparison(result, "고객명")
        assert comp is not None
        assert comp.status == "일치"

    def test_고객명_명백한_불일치(self):
        verifier = CrossVerifier()
        analysis = _analysis(
            fields={
                "고객명": "김철수",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            }
        )
        result = verifier.verify(
            analysis, _reservation(customer_name="박성구"), _submission()
        )
        comp = _get_comparison(result, "고객명")
        assert comp is not None
        assert comp.status == "불일치"

    def test_예약번호_완전일치(self):
        verifier = CrossVerifier()
        result = verifier.verify(_analysis(), _reservation(), _submission())
        comp = _get_comparison(result, "예약번호")
        assert comp is not None
        assert comp.status == "일치"

    def test_예약번호_불일치(self):
        verifier = CrossVerifier()
        analysis = _analysis(
            fields={
                "고객명": "박성구",
                "예약번호": "OR9999999",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            }
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        comp = _get_comparison(result, "예약번호")
        assert comp is not None
        assert comp.status == "불일치"

    def test_날짜_예약기간_범위내_일치(self):
        verifier = CrossVerifier()
        result = verifier.verify(_analysis(), _reservation(), _submission())
        comp = _get_comparison(result, "날짜")
        assert comp is not None
        assert comp.status == "일치"

    def test_날짜_예약기간_하루전도_허용(self):
        verifier = CrossVerifier()
        # start is 2026-02-27, so start-1day is 2026-02-26
        analysis = _analysis(
            fields={
                "고객명": "박성구",
                "예약번호": "OR2017576",
                "날짜": "2026-02-26",
                "결항사유": "기상악화",
            }
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        comp = _get_comparison(result, "날짜")
        assert comp is not None
        assert comp.status == "일치"

    def test_날짜_예약기간_범위밖_불일치(self):
        verifier = CrossVerifier()
        analysis = _analysis(
            fields={
                "고객명": "박성구",
                "예약번호": "OR2017576",
                "날짜": "2026-03-15",
                "결항사유": "기상악화",
            }
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        comp = _get_comparison(result, "날짜")
        assert comp is not None
        assert comp.status == "불일치"

    def test_연락처_숫자만_비교_일치(self):
        verifier = CrossVerifier()
        # submission phone differs in format from reservation phone
        result = verifier.verify(
            _analysis(),
            _reservation(phone="010-6680-0292"),
            _submission(phone="01066800292"),
        )
        comp = _get_comparison(result, "연락처")
        assert comp is not None
        assert comp.status == "일치"

    def test_연락처_불일치(self):
        verifier = CrossVerifier()
        result = verifier.verify(
            _analysis(),
            _reservation(phone="010-1111-2222"),
            _submission(phone="010-3333-4444"),
        )
        comp = _get_comparison(result, "연락처")
        assert comp is not None
        assert comp.status == "불일치"

    def test_추출필드_빈값이면_확인불가(self):
        # Use 해운사 document_type so empty name is NOT 비교불필요
        verifier = CrossVerifier()
        analysis = _analysis(
            document_type="해운사 결항확인서",
            fields={
                "고객명": "",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        comp = _get_comparison(result, "고객명")
        assert comp is not None
        assert comp.status == "확인불가"

    def test_추출필드_None이면_확인불가(self):
        # Use 해운사 document_type so None name is NOT 비교불필요
        verifier = CrossVerifier()
        analysis = _analysis(
            document_type="해운사 결항확인서",
            fields={
                "고객명": None,
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        comp = _get_comparison(result, "고객명")
        assert comp is not None
        assert comp.status == "확인불가"


class TestAirlineDocumentException:
    def test_항공사문서_고객명_미기재_비교불필요(self):
        verifier = CrossVerifier()
        analysis = _analysis(
            document_type="항공사 운항정보확인서",
            fields={
                "고객명": "",
                "예약번호": "",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        comp = _get_comparison(result, "고객명")
        assert comp is not None
        assert comp.status == "비교불필요"

    def test_항공사문서_예약번호_미기재_비교불필요(self):
        verifier = CrossVerifier()
        analysis = _analysis(
            document_type="항공사 운항정보확인서",
            fields={
                "고객명": "",
                "예약번호": "",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        comp = _get_comparison(result, "예약번호")
        assert comp is not None
        assert comp.status == "비교불필요"

    def test_해운사문서_고객명_미기재는_확인불가(self):
        verifier = CrossVerifier()
        analysis = _analysis(
            document_type="해운사 결항확인서",
            fields={
                "고객명": "",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        comp = _get_comparison(result, "고객명")
        assert comp is not None
        assert comp.status == "확인불가"


class TestRuleBasedVerdict:
    def test_모든_필드_일치시_승인(self):
        verifier = CrossVerifier()
        result = verifier.verify(_analysis(), _reservation(), _submission())
        assert result.verdict == "승인"

    def test_고객명_불일치_하나라도_있으면_반려(self):
        verifier = CrossVerifier()
        analysis = _analysis(
            fields={
                "고객명": "김철수",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            }
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        assert result.verdict == "반려"

    def test_문서유형_기타이면_AI위임_없으면_보류(self):
        verifier = CrossVerifier(gateway=None)
        analysis = _analysis(
            document_type="기타",
            fields={
                "고객명": "박성구",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        assert result.verdict == "보류"

    def test_문서유형_None이면_보류(self):
        verifier = CrossVerifier(gateway=None)
        analysis = _analysis(
            document_type=None,
            fields={
                "고객명": "박성구",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        assert result.verdict == "보류"

    def test_결항사유_미추출이면_AI위임_없으면_보류(self):
        verifier = CrossVerifier(gateway=None)
        analysis = _analysis(
            fields={
                "고객명": "박성구",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "",
            }
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        assert result.verdict == "보류"

    def test_이미지품질_문제시_보류(self):
        verifier = CrossVerifier(gateway=None)
        analysis = _analysis(quality_issues=["이미지가 흐릿합니다"])
        result = verifier.verify(analysis, _reservation(), _submission())
        assert result.verdict == "보류"

    def test_확인불가_필드만_있으면_승인_아닌_보류(self):
        # 해운사 doc: identity fields all 확인불가 → not enough evidence → 보류
        verifier = CrossVerifier(gateway=None)
        analysis = _analysis(
            document_type="해운사 결항확인서",
            fields={
                "고객명": "",
                "예약번호": "",
                "날짜": "2026-02-27",
                "결항사유": "악천후",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        assert result.verdict == "보류"

    def test_항공사문서_비교불필요_포함_승인(self):
        # Airline doc: name/key are 비교불필요, date matches → should still reach 승인
        verifier = CrossVerifier()
        analysis = _analysis(
            document_type="항공사 운항정보확인서",
            fields={
                "고객명": "",
                "예약번호": "",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        assert result.verdict == "승인"


class TestAIFallback:
    def test_애매한_케이스_ai_호출(self):
        gemini = FakeGeminiClient(result={"verdict": "승인", "reasoning": "AI 판단"})
        verifier = CrossVerifier(gateway=gemini)
        analysis = _analysis(
            document_type="기타",
            fields={
                "고객명": "박성구",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        verifier.verify(analysis, _reservation(), _submission())
        assert len(gemini.calls) == 1

    def test_ai_승인_판단_반영(self):
        gemini = FakeGeminiClient(
            result={"verdict": "승인", "reasoning": "AI 승인 이유"}
        )
        verifier = CrossVerifier(gateway=gemini)
        analysis = _analysis(
            document_type="기타",
            fields={
                "고객명": "박성구",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        assert result.verdict == "승인"
        assert result.ai_used is True
        assert result.ai_reasoning == "AI 승인 이유"

    def test_ai_반려_판단_반영(self):
        gemini = FakeGeminiClient(
            result={"verdict": "반려", "reasoning": "불일치 발견"}
        )
        verifier = CrossVerifier(gateway=gemini)
        analysis = _analysis(
            document_type="기타",
            fields={
                "고객명": "박성구",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        assert result.verdict == "반려"
        assert result.ai_used is True

    def test_ai_실패시_보류_반환(self):
        gemini = FakeGeminiClient(result=Exception("API 오류"))
        verifier = CrossVerifier(gateway=gemini)
        analysis = _analysis(
            document_type="기타",
            fields={
                "고객명": "박성구",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        assert result.verdict == "보류"
        assert result.ai_used is True

    def test_gateway_없으면_ai_스킵_보류(self):
        verifier = CrossVerifier(gateway=None)
        analysis = _analysis(
            document_type="기타",
            fields={
                "고객명": "박성구",
                "예약번호": "OR2017576",
                "날짜": "2026-02-27",
                "결항사유": "기상악화",
            },
        )
        result = verifier.verify(analysis, _reservation(), _submission())
        assert result.verdict == "보류"
        assert result.ai_used is False
