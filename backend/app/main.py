import asyncio
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

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

_BUILDING_HUB_BASE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
_BUILDING_HUB_ROWS = 1000


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return (
        value.replace(" ", "")
        .replace("번지", "")
        .replace("호", "")
        .replace("(", "")
        .replace(")", "")
    )


def _summarize_building_item(item: dict[str, str]) -> dict[str, str]:
    address = item.get("newPlatPlc") or item.get("platPlc") or ""
    return {
        "building_name": item.get("bldNm", "").strip() or address,
        "address": address.strip(),
        "lot_address": item.get("platPlc", "").strip(),
        "regstr_kind": item.get("regstrKindCdNm", "").strip(),
        "building_type": item.get("mainPurpsCdNm", "").strip(),
        "detail_use": item.get("etcPurps", "").strip(),
        "structure": item.get("strctCdNm", "").strip(),
        "roof": item.get("roofCdNm", "").strip(),
        "floors": item.get("grndFlrCnt", "").strip(),
        "basements": item.get("ugrndFlrCnt", "").strip(),
        "households": item.get("hhldCnt", "").strip(),
        "family_count": item.get("fmlyCnt", "").strip(),
        "use_approval_date": item.get("useAprDay", "").strip(),
        "completion_date": item.get("stcnsDay", "").strip(),
        "permission_date": item.get("pmsDay", "").strip(),
        "resistant_quake": item.get("rserthqkDsgnApplyYn", "").strip(),
        "legal_code": item.get("bjdongCd", "").strip(),
        "sigungu_code": item.get("sigunguCd", "").strip(),
    }


async def _reverse_geocode(client: httpx.AsyncClient, lat: float, lng: float) -> dict[str, str]:
    response = await client.get(
        "https://maps.apigw.ntruss.com/map-reversegeocode/v2/gc",
        params={
            "coords": f"{lng},{lat}",
            "orders": "legalcode,admcode,addr",
            "output": "json",
        },
        headers={
            "X-NCP-APIGW-API-KEY-ID": settings.naver_maps_client_id,
            "X-NCP-APIGW-API-KEY": settings.naver_maps_client_secret,
        },
        timeout=10.0,
    )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Naver reverse geocoding API 호출 실패")

    payload = response.json()
    results = payload.get("results") or []
    if not results:
        return {}

    legal = next((result for result in results if result.get("name") == "legalcode"), None)
    addr = next((result for result in results if result.get("name") == "addr"), None)
    adm = next((result for result in results if result.get("name") == "admcode"), None)

    legal_code = ((legal or {}).get("code") or {}).get("id") or ""
    road_address = (((addr or {}).get("region") or {}).get("area1") or {}).get("name", "").strip()
    road_address = " ".join(
        part
        for part in [
            (((addr or {}).get("region") or {}).get("area1") or {}).get("name", "").strip(),
            (((addr or {}).get("region") or {}).get("area2") or {}).get("name", "").strip(),
            (((addr or {}).get("region") or {}).get("area3") or {}).get("name", "").strip(),
            (((addr or {}).get("region") or {}).get("area4") or {}).get("name", "").strip(),
        ]
        if part
    ).strip()
    land = (legal or {}).get("land") or {}
    land_number_1 = (land.get("number1") or "").strip()
    land_number_2 = (land.get("number2") or "").strip()
    lot_number = land_number_1
    if land_number_2 and land_number_2 != "0":
        lot_number = f"{land_number_1}-{land_number_2}"
    jibun_address = " ".join(
        part
        for part in [
            (((legal or {}).get("region") or {}).get("area1") or {}).get("name", "").strip(),
            (((legal or {}).get("region") or {}).get("area2") or {}).get("name", "").strip(),
            (((legal or {}).get("region") or {}).get("area3") or {}).get("name", "").strip(),
            (((legal or {}).get("region") or {}).get("area4") or {}).get("name", "").strip(),
            lot_number,
        ]
        if part
    ).strip()
    adm_code = ((adm or {}).get("code") or {}).get("id") or ""

    return {
        "legal_code": legal_code,
        "sigungu_cd": legal_code[:5] if len(legal_code) >= 5 else "",
        "bjdong_cd": legal_code[5:] if len(legal_code) >= 10 else "",
        "road_address": road_address,
        "jibun_address": jibun_address,
        "adm_code": adm_code,
    }


async def _fetch_building_register_page(
    client: httpx.AsyncClient,
    sigungu_cd: str,
    bjdong_cd: str,
    page_no: int,
) -> tuple[int, list[dict[str, str]]]:
    if not settings.data_go_kr_api_key:
        raise HTTPException(status_code=500, detail="DATA_GO_KR_API_KEY가 설정되지 않았습니다.")

    response = await client.get(
        _BUILDING_HUB_BASE_URL,
        params={
            "serviceKey": unquote(settings.data_go_kr_api_key),
            "sigunguCd": sigungu_cd,
            "bjdongCd": bjdong_cd,
            "platGbCd": "0",
            "numOfRows": _BUILDING_HUB_ROWS,
            "pageNo": page_no,
        },
        timeout=20.0,
    )
    if response.status_code != 200:
        return 0, []

    root = ET.fromstring(response.text)
    if root.findtext(".//resultCode") != "00":
        return 0, []

    total_count = int(root.findtext(".//totalCount") or "0")
    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        items.append({child.tag: (child.text or "") for child in list(item)})
    return total_count, items


async def _fetch_building_register_items(
    client: httpx.AsyncClient,
    sigungu_cd: str,
    bjdong_cd: str,
) -> tuple[int, list[dict[str, str]]]:
    total_count, first_page_items = await _fetch_building_register_page(client, sigungu_cd, bjdong_cd, 1)
    if total_count <= len(first_page_items):
        return total_count, first_page_items

    total_pages = (total_count + _BUILDING_HUB_ROWS - 1) // _BUILDING_HUB_ROWS
    tasks = [
        _fetch_building_register_page(client, sigungu_cd, bjdong_cd, page_no)
        for page_no in range(2, total_pages + 1)
    ]
    results = await asyncio.gather(*tasks) if tasks else []

    items = list(first_page_items)
    for _, page_items in results:
        items.extend(page_items)
    return total_count, items


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


@app.get("/building-register")
async def get_building_register(
    lat: float = Query(..., description="위도"),
    lng: float = Query(..., description="경도"),
):
    if not settings.naver_maps_client_id or not settings.naver_maps_client_secret:
        raise HTTPException(status_code=500, detail="Naver Maps API 키가 설정되지 않았습니다.")
    if not settings.data_go_kr_api_key:
        raise HTTPException(status_code=500, detail="DATA_GO_KR_API_KEY가 설정되지 않았습니다.")

    async with httpx.AsyncClient() as client:
        location = await _reverse_geocode(client, lat, lng)
        sigungu_cd = location.get("sigungu_cd", "")
        bjdong_cd = location.get("bjdong_cd", "")
        if not sigungu_cd or not bjdong_cd:
            raise HTTPException(status_code=404, detail="법정동 코드를 찾지 못했습니다.")

        total_count, items = await _fetch_building_register_items(client, sigungu_cd, bjdong_cd)
        if not items:
            return {
                "location": location,
                "total_count": total_count,
                "matched_count": 0,
                "selected": None,
                "candidates": [],
            }

        target_tokens = [
            _normalize_text(location.get("jibun_address")),
            _normalize_text(location.get("road_address")),
        ]

        candidates: list[dict[str, str]] = []
        for item in items:
            item_tokens = [
                _normalize_text(item.get("platPlc")),
                _normalize_text(item.get("newPlatPlc")),
            ]
            if any(target and any(target in item_token or item_token in target for item_token in item_tokens) for target in target_tokens):
                candidates.append(item)

        selected_item = candidates[0] if candidates else items[0]
        summary = _summarize_building_item(selected_item)
        candidate_source = candidates if candidates else items[:20]

        return {
            "location": location,
            "total_count": total_count,
            "matched_count": len(candidates) if candidates else 1,
            "selected": summary,
            "candidates": [_summarize_building_item(item) for item in candidate_source],
        }


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
