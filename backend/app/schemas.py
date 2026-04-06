from typing import Literal

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


class HealthResponse(BaseModel):
    status: Literal["ok"]


class RootResponse(BaseModel):
    message: str
    docs_url: str
    health_url: str
