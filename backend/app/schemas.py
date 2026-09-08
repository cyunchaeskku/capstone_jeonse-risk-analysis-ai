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


class RegistryMaxClaimItem(BaseModel):
    amount_krw: int
    raw_text: str
    page: int | None = None
    collateral_list_no: str | None = None
    shared_property_count: int = Field(default=1, ge=1, description="공동담보목록에 묶인 물건 수. 단독담보면 1")


class RegistryParseResponse(BaseModel):
    filename: str
    max_claim_amount_krw: int | None = None
    max_claim_amounts: list[RegistryMaxClaimItem] = Field(default_factory=list)
    status: Literal["parsed", "needs_review"]
    message: str


class RegistryInspectResponse(BaseModel):
    filename: str
    max_claim_amount_krw: int | None = None
    max_claim_amounts: list[RegistryMaxClaimItem] = Field(default_factory=list)
    inspection: dict[str, Any] = Field(default_factory=dict)
    status: Literal["inspected", "needs_review"]
    message: str


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
    risk_score: int


RiskGrade = Literal["safe", "caution", "risk", "high_risk"]


class MortgageItem(BaseModel):
    """근저당 한 건. 공동담보면 하나의 채권최고액이 여러 물건에 걸린다."""

    amount_krw: int = Field(..., ge=0, description="채권최고액 원문 금액")
    shared_property_count: int = Field(..., ge=1, description="공동담보목록에 묶인 물건 수. 단독담보면 1")


class RiskAssessRequest(BaseModel):
    """R1~R8 마법사가 수집한 입력. 모든 필드는 필수이며, 미확보는 빈 값으로 보내 `unknown`으로 판정한다."""

    listing_name: str = Field(..., min_length=1, description="매물명 또는 주소")
    deposit_krw: int = Field(..., ge=0, description="내 보증금 (R1·R2-b·R8)")
    market_price_krw: int = Field(..., ge=0, description="주택 시세. 0이면 미확보 → R1·R2·R8 unknown")
    registry_type: Literal["aggregate_building", "general_building", "unknown"] = Field(
        ..., description="등기 유형. R2는 집합건물에서만, R8은 일반건물에서만 판정한다"
    )
    mortgage_total_krw: int = Field(..., ge=0, description="말소되지 않은 채권최고액 합계 원문 (R8)")
    mortgage_items: list[MortgageItem] = Field(
        ...,
        description="말소되지 않은 근저당별 채권최고액과 공동담보 물건 수 (R2). 공동담보는 민법 368①에 따라 배분한다",
    )
    registry_owner_name: str = Field(..., description="등기부 갑구 현재 소유자명. 빈 문자열이면 미확보 (R3)")
    contract_owner_name: str = Field(..., description="계약서상 임대인명. 빈 문자열이면 미확보 (R3)")
    critical_terms: list[dict[str, Any]] = Field(
        default_factory=list, description="등기부에서 추출한 압류·가압류·가처분·가등기·경매·신탁 항목 (R4)"
    )
    building_type: str = Field(..., description="건축물 주용도 (R5)")
    detail_use: str = Field(..., description="건축물 기타용도 (R5)")
    illegal_building_status: Literal["present", "absent", "unclear"] = Field(
        ...,
        description="건축물대장 위반건축물 표시 (R6). 확인하지 못했으면 unclear",
    )
    recent_jeonse_count: int = Field(..., ge=0, description="동일 건물 최근 3년 순수 전세 거래 건수 (R7)")
    recent_jeonse_peak_12m_count: int = Field(..., ge=0, description="최근 3년 중 가장 집중된 12개월의 신규 전세 건수 (R7)")
    households: int = Field(..., ge=0, description="건축물대장 총 세대수. 0이면 미확보 (R7)")
    recent_jeonse_data_status: Literal["complete", "partial", "unavailable", "manual"] = Field(
        ..., description="R7 전월세 데이터 조회 상태. 실제 0건과 조회 실패를 구분한다"
    )
    senior_deposit_krw: int | None = Field(
        ..., ge=0, description="선순위 보증금 합계 (R8). 확인하지 못했으면 null"
    )


class RiskAssessResponse(BaseModel):
    checks: list[ListingCheckResult]
    summary: ListingCheckSummary
    risk_score: int
    risk_grade: RiskGrade
    override_reasons: list[str] = Field(default_factory=list)
    llm_explanation: str
