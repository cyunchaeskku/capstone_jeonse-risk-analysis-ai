from uuid import uuid4

from .schemas import AnalysisCreateRequest, AnalysisCreateResponse, AnalysisDetailResponse, RiskFactor


class AnalysisService:
    def __init__(self) -> None:
        self._items: dict[str, AnalysisDetailResponse] = {}

    def create_analysis(self, payload: AnalysisCreateRequest) -> AnalysisCreateResponse:
        analysis_id = str(uuid4())
        risk_factors = self._build_risk_factors(payload)
        overall_risk = self._aggregate_risk(risk_factors)
        references = [
            "입력된 매물 정보",
            "입력된 계약 정보",
        ]
        if payload.documents:
            references.append("업로드 문서 메타데이터")

        detail = AnalysisDetailResponse(
            analysis_id=analysis_id,
            status="completed",
            overall_risk=overall_risk,
            risk_factors=risk_factors,
            explanation=self._build_explanation(overall_risk, risk_factors),
            references=references,
        )
        self._items[analysis_id] = detail

        return AnalysisCreateResponse(
            analysis_id=analysis_id,
            status="completed",
            normalized_summary={
                "address": payload.property.address,
                "deposit_krw": payload.property.deposit_krw,
                "document_count": len(payload.documents),
            },
        )

    def get_analysis(self, analysis_id: str) -> AnalysisDetailResponse | None:
        return self._items.get(analysis_id)

    def _build_risk_factors(self, payload: AnalysisCreateRequest) -> list[RiskFactor]:
        factors: list[RiskFactor] = []

        deposit = payload.property.deposit_krw
        if deposit >= 500_000_000:
            factors.append(
                RiskFactor(
                    code="HIGH_DEPOSIT",
                    title="고액 보증금",
                    level="high",
                    detail="보증금이 높아 추가 권리관계 확인 필요성이 큽니다.",
                )
            )
        elif deposit >= 200_000_000:
            factors.append(
                RiskFactor(
                    code="MID_DEPOSIT",
                    title="중간 이상 보증금",
                    level="medium",
                    detail="보증금 규모가 커서 등기와 선순위 권리 확인이 필요합니다.",
                )
            )
        else:
            factors.append(
                RiskFactor(
                    code="LOW_DEPOSIT",
                    title="상대적으로 낮은 보증금",
                    level="low",
                    detail="보증금 기준 위험도는 상대적으로 낮습니다.",
                )
            )

        if not payload.documents:
            factors.append(
                RiskFactor(
                    code="MISSING_DOCUMENTS",
                    title="문서 미업로드",
                    level="medium",
                    detail="계약서나 등기부등본 등 검토 문서가 없어 판단 근거가 제한됩니다.",
                )
            )
        else:
            factors.append(
                RiskFactor(
                    code="DOCUMENTS_ATTACHED",
                    title="기초 문서 첨부",
                    level="low",
                    detail="문서 메타데이터가 포함되어 후속 검토 확장이 가능합니다.",
                )
            )

        return factors

    def _aggregate_risk(self, factors: list[RiskFactor]) -> str:
        if any(factor.level == "high" for factor in factors):
            return "high"
        if any(factor.level == "medium" for factor in factors):
            return "medium"
        return "low"

    def _build_explanation(self, overall_risk: str, factors: list[RiskFactor]) -> str:
        factor_titles = ", ".join(factor.title for factor in factors)
        return (
            f"현재 입력 기준 종합 위험도는 '{overall_risk}'입니다. "
            f"주요 판단 요소는 {factor_titles} 입니다."
        )
