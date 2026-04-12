from typing import Any, Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high"]


class PropertyInfo(BaseModel):
    address: str = Field(..., description="Property address")
    deposit_krw: int = Field(..., ge=0, description="Jeonse deposit amount in KRW")
    monthly_rent_krw: int = Field(0, ge=0, description="Optional monthly rent in KRW")
    building_type: str | None = Field(None, description="Apartment, villa, officetel, etc.")


class ContractInfo(BaseModel):
    landlord_name: str | None = None
    contract_start_date: str | None = Field(None, description="YYYY-MM-DD")
    contract_end_date: str | None = Field(None, description="YYYY-MM-DD")
    special_terms: list[str] = Field(default_factory=list)


class DocumentRef(BaseModel):
    document_type: str = Field(..., description="contract, registry, id-card, etc.")
    filename: str = Field(..., description="Original filename")


class AnalysisCreateRequest(BaseModel):
    property: PropertyInfo
    contract: ContractInfo | None = None
    documents: list[DocumentRef] = Field(default_factory=list)


class AnalysisCreateResponse(BaseModel):
    analysis_id: str
    status: Literal["completed"]
    normalized_summary: dict[str, object]


class RiskFactor(BaseModel):
    code: str
    title: str
    level: RiskLevel
    detail: str


class LegalSource(BaseModel):
    citation_label: str
    law_name: str
    jo_code: str | None = None
    article_number: str | None = None
    article_title: str | None = None
    score: float | None = None
    excerpt: str | None = None


class AnalysisDetailResponse(BaseModel):
    analysis_id: str
    status: Literal["completed"]
    overall_risk: RiskLevel
    risk_factors: list[RiskFactor]
    explanation: str
    references: list[str]


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(..., min_length=1)


class QaRequest(BaseModel):
    question: str = Field(..., min_length=1)
    analysis_id: str | None = None
    history: list[ChatHistoryMessage] = Field(default_factory=list)


class QaResponse(BaseModel):
    answer: str
    references: list[str]
    disclaimer: str
    scope: Literal["jeonse-legal-assistant"]
    route: Literal["simple", "legal"]
    sources: list[LegalSource] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"]


class RootResponse(BaseModel):
    message: str
    docs_url: str
    health_url: str


ListingCheckStatus = Literal["pass", "warn", "fail", "unknown"]


class ListingCheckAnalyzeRequest(BaseModel):
    property_type: Literal["apt", "offi", "rh", "sh"] = Field(..., description="매물 종류")
    listing_name: str = Field(..., min_length=1, description="사용자가 선택한 매물명")
    deposit_krw: int = Field(..., ge=0, description="전세 보증금 (KRW)")
    market_price_krw: int | None = Field(default=None, ge=0, description="시세 (KRW). 없으면 provider가 산출")
    selected_rent_item: dict[str, Any] = Field(default_factory=dict, description="선택된 전월세 거래 스냅샷")
    selected_building: dict[str, Any] = Field(default_factory=dict, description="선택된 건축물대장 스냅샷")
    extra_signals: dict[str, Any] = Field(default_factory=dict, description="향후 확장 신호 입력")


class ListingCheckResult(BaseModel):
    code: str
    title: str
    status: ListingCheckStatus
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class ListingCheckSummary(BaseModel):
    overall_status: ListingCheckStatus
    triggered_checks: list[str] = Field(default_factory=list)


class ListingCheckAnalyzeResponse(BaseModel):
    checks: list[ListingCheckResult]
    summary: ListingCheckSummary
    llm_explanation: str
