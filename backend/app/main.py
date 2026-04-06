from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .chatbot import ChatbotService
from .schemas import (
    AnalysisCreateRequest,
    AnalysisCreateResponse,
    AnalysisDetailResponse,
    HealthResponse,
    QaRequest,
    QaResponse,
    RootResponse,
)
from .services import AnalysisService
from .settings import settings


app = FastAPI(
    title="Jeonse Risk Analysis API",
    version="0.1.0",
    description="초기 개발용 FastAPI 백엔드",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = AnalysisService()
chatbot_service = ChatbotService()


@app.get("/", response_model=RootResponse)
def read_root() -> RootResponse:
    return RootResponse(
        message="Welcome to the Jeonse Risk Analysis API.",
        docs_url="/docs",
        health_url="/health",
    )


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/analyses", response_model=AnalysisCreateResponse)
def create_analysis(payload: AnalysisCreateRequest) -> AnalysisCreateResponse:
    return service.create_analysis(payload)


@app.get("/analyses/{analysis_id}", response_model=AnalysisDetailResponse)
def get_analysis(analysis_id: str) -> AnalysisDetailResponse:
    item = service.get_analysis(analysis_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ANALYSIS_NOT_FOUND",
                "message": "해당 분석 요청을 찾을 수 없습니다.",
                "action_hint": "분석 ID를 다시 확인하거나 새 분석을 생성하세요.",
            },
        )
    return item


@app.post("/qa", response_model=QaResponse)
def answer_question(payload: QaRequest) -> QaResponse:
    analysis = service.get_analysis(payload.analysis_id) if payload.analysis_id else None
    try:
        return chatbot_service.answer_question(
            question=payload.question,
            history=payload.history,
            analysis=analysis,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CHATBOT_NOT_CONFIGURED",
                "message": str(error),
                "action_hint": "OPENAI_API_KEY를 설정한 뒤 서버를 다시 시작하세요.",
            },
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "CHATBOT_UPSTREAM_ERROR",
                "message": "챗봇 응답 생성 중 외부 모델 호출에 실패했습니다.",
                "action_hint": "잠시 후 다시 시도하세요.",
            },
        ) from error
