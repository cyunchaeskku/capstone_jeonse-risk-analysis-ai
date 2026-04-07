import asyncio
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
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


@app.get("/geocode")
async def geocode(query: str = Query(..., description="검색할 주소")):
    if not settings.naver_maps_client_id or not settings.naver_maps_client_secret:
        raise HTTPException(status_code=500, detail="Naver Maps API 키가 설정되지 않았습니다.")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://maps.apigw.ntruss.com/map-geocode/v2/geocode",
            params={"query": query},
            headers={
                "X-NCP-APIGW-API-KEY-ID": settings.naver_maps_client_id,
                "X-NCP-APIGW-API-KEY": settings.naver_maps_client_secret,
            },
        )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Naver Geocoding API 호출 실패")
    data = response.json()
    addresses = data.get("addresses", [])
    if not addresses:
        return {"result": None}
    first = addresses[0]
    return {"result": {"x": first["x"], "y": first["y"], "address": first["roadAddress"] or first["jibunAddress"]}}


_LAWD_CD_MAP: dict = json.loads(
    (Path(__file__).parent / "data" / "lawd_cd_map.json").read_text(encoding="utf-8")
)


_PROPERTY_TYPE_MAP = {
    # (서비스명, 메서드명, 건물명XML필드, 면적XML필드)
    "apt":  ("RTMSDataSvcAptRent",  "getRTMSDataSvcAptRent",  "aptNm",     "excluUseAr"),
    "offi": ("RTMSDataSvcOffiRent", "getRTMSDataSvcOffiRent", "offiNm",    "excluUseAr"),
    "rh":   ("RTMSDataSvcRHRent",   "getRTMSDataSvcRHRent",   "mhouseNm",  "excluUseAr"),
    "sh":   ("RTMSDataSvcSHRent",   "getRTMSDataSvcSHRent",   "houseType", "totalFloorAr"),
}


def _iter_months(start: str, end: str) -> list[str]:
    """'202511' ~ '202601' 사이의 YYYYMM 목록 반환 (최대 24개월)"""
    sy, sm = int(start[:4]), int(start[4:])
    ey, em = int(end[:4]), int(end[4:])
    months = []
    y, m = sy, sm
    while (y * 100 + m) <= (ey * 100 + em):
        months.append(f"{y}{str(m).zfill(2)}")
        m += 1
        if m > 12:
            m = 1
            y += 1
        if len(months) >= 24:
            break
    return months


async def _fetch_month(client: httpx.AsyncClient, svc_name: str, method_name: str, building_field: str, area_field: str, lawd_cd: str, ymd: str, dong: str) -> list[dict]:
    url = (
        f"https://apis.data.go.kr/1613000/{svc_name}/{method_name}"
        f"?serviceKey={settings.data_go_kr_api_key}"
        f"&LAWD_CD={lawd_cd}&DEAL_YMD={ymd}&numOfRows=1000&pageNo=1"
    )
    response = await client.get(url, timeout=10.0)
    if response.status_code != 200:
        return []
    root = ET.fromstring(response.text)
    if root.findtext(".//resultCode") != "000":
        return []
    items = root.findall(".//item")
    result = []
    for item in items:
        if dong and dong not in (item.findtext("umdNm") or ""):
            continue
        result.append({
            "buildingNm": item.findtext(building_field),
            "umdNm": item.findtext("umdNm"),
            "excluUseAr": item.findtext(area_field),
            "deposit": item.findtext("deposit"),
            "monthlyRent": item.findtext("monthlyRent"),
            "floor": item.findtext("floor"),
            "contractType": item.findtext("contractType"),
            "dealYear": item.findtext("year"),
            "dealMonth": item.findtext("month"),
            "dealDay": item.findtext("day"),
        })
    return result


@app.get("/jeonse-data")
async def get_jeonse_data(
    sido: str = Query(..., description="시도명 (예: 경기도)"),
    sigungu: str = Query(..., description="시군구명 (예: 수원시 권선구)"),
    dong: str = Query(default="", description="읍면동명 (예: 탑동, 생략 시 전체)"),
    deal_from: str = Query(..., description="시작 계약년월 6자리 (예: 202511)"),
    deal_to: str = Query(..., description="종료 계약년월 6자리 (예: 202601)"),
    property_type: str = Query(default="apt", description="매물 종류: apt(아파트), offi(오피스텔), rh(연립/다세대), sh(단독/다가구)"),
):
    if not settings.data_go_kr_api_key:
        raise HTTPException(status_code=500, detail="DATA_GO_KR_API_KEY가 설정되지 않았습니다.")

    if property_type not in _PROPERTY_TYPE_MAP:
        raise HTTPException(status_code=400, detail=f"알 수 없는 매물 종류: {property_type}")

    sigungu_map = _LAWD_CD_MAP.get(sido)
    if sigungu_map is None:
        raise HTTPException(status_code=400, detail=f"알 수 없는 시도명: {sido}")
    lawd_cd = sigungu_map.get(sigungu)
    if lawd_cd is None:
        raise HTTPException(status_code=400, detail=f"알 수 없는 시군구명: {sigungu}")

    if deal_from > deal_to:
        raise HTTPException(status_code=400, detail="deal_from이 deal_to보다 클 수 없습니다.")

    months = _iter_months(deal_from, deal_to)
    svc_name, method_name, building_field, area_field = _PROPERTY_TYPE_MAP[property_type]

    async with httpx.AsyncClient() as client:
        tasks = [_fetch_month(client, svc_name, method_name, building_field, area_field, lawd_cd, ymd, dong) for ymd in months]
        results_per_month = await asyncio.gather(*tasks)

    result = [item for month_items in results_per_month for item in month_items]
    return {"lawd_cd": lawd_cd, "deal_from": deal_from, "deal_to": deal_to, "total": len(result), "items": result}


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
