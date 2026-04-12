import asyncio
import csv
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import date
from typing import Any, Protocol
from urllib.parse import unquote

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .chatbot import ChatbotService
from .schemas import (
    AnalysisCreateRequest,
    AnalysisCreateResponse,
    AnalysisDetailResponse,
    HealthResponse,
    ListingCheckAnalyzeRequest,
    ListingCheckAnalyzeResponse,
    ListingCheckResult,
    ListingCheckSummary,
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

_CSV_PATH = Path(__file__).parent.parent.parent / "data" / "address_code.csv"


def _load_legal_code_map():
    mapping = {}
    if not _CSV_PATH.exists():
        return mapping
    try:
        with open(_CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("삭제일자") and row["삭제일자"].strip():
                    continue
                sido = (row.get("시도명") or "").strip()
                sig = (row.get("시군구명") or "").strip()
                eup = (row.get("읍면동명") or "").strip()
                code = (row.get("법정동코드") or "").strip()
                if code:
                    mapping[(sido, sig, eup)] = code
    except Exception as e:
        print(f"Error loading legal code CSV: {e}")
    return mapping


_CSV_LEGAL_CODE_MAP = _load_legal_code_map()


def _lookup_legal_code(address_str: str) -> str | None:
    words = address_str.split()
    if not words:
        return None

    sido = words[0]
    # Normalize '세종특별자치시'
    if sido == "세종특별자치시" and len(words) >= 2:
        # Sejong case
        key = ("세종특별자치시", "세종시", words[1])
        if key in _CSV_LEGAL_CODE_MAP:
            return _CSV_LEGAL_CODE_MAP[key]

    # Try matching first few words
    for i in range(1, min(len(words), 5)):
        eup = words[i]
        sig = " ".join(words[1:i])
        key = (sido, sig, eup)
        if key in _CSV_LEGAL_CODE_MAP:
            return _CSV_LEGAL_CODE_MAP[key]

    return None

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


def _remove_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


@app.get("/places/search")
async def search_places(query: str = Query(..., description="검색할 장소명")):
    if not settings.naver_search_client_id or not settings.naver_search_client_secret:
        raise HTTPException(status_code=500, detail="Naver Search API 키가 설정되지 않았습니다.")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://openapi.naver.com/v1/search/local.json",
            params={"query": query, "display": 10},
            headers={
                "X-Naver-Client-Id": settings.naver_search_client_id,
                "X-Naver-Client-Secret": settings.naver_search_client_secret,
            },
            timeout=10.0,
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Naver Search API 호출 실패")

    data = response.json()
    items = data.get("items", [])

    results = []
    for item in items:
        results.append({
            "title": _remove_tags(item.get("title", "")),
            "roadAddress": item.get("roadAddress", ""),
            "address": item.get("address", ""),
            "category": item.get("category", ""),
            "mapx": item.get("mapx", ""),
            "mapy": item.get("mapy", ""),
        })

    return {"items": results}


def _summarize_building_item(item: dict[str, str]) -> dict[str, str]:
    address = item.get("newPlatPlc") or item.get("platPlc") or ""
    return {
        "mgmBldrgstPk": item.get("mgmBldrgstPk", "").strip(),
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


async def _geocode_query(client: httpx.AsyncClient, query: str) -> dict[str, str] | None:
    response = await client.get(
        "https://maps.apigw.ntruss.com/map-geocode/v2/geocode",
        params={"query": query},
        headers={
            "X-NCP-APIGW-API-KEY-ID": settings.naver_maps_client_id,
            "X-NCP-APIGW-API-KEY": settings.naver_maps_client_secret,
        },
        timeout=10.0,
    )
    if response.status_code != 200:
        return None
    data = response.json()
    addresses = data.get("addresses", [])
    if not addresses:
        return None
    first = addresses[0]
    return {
        "x": first["x"],
        "y": first["y"],
        "address": first["roadAddress"] or first["jibunAddress"],
    }


def _extract_bun_ji(address_str: str) -> tuple[str, str]:
    """주소 문자열에서 번(bun)과 지(ji)를 추출 (예: '연향동 1658-1' -> ('1658', '1'))"""
    parts = address_str.strip().split()
    if not parts:
        return "", ""
    
    last_part = parts[-1]
    # 번지 형식 (숫자-숫자 또는 숫자) 인지 확인
    match = re.search(r"(\d+)(?:-(\d+))?$", last_part)
    if match:
        bun = match.group(1).zfill(4)
        # ji가 없거나 0이면 공백으로 두어 API가 전체 필지를 조회하게 함
        ji = match.group(2).zfill(4) if match.group(2) and match.group(2) != "0" else ""
        return bun, ji
    return "", ""


async def _fetch_building_register_page(
    client: httpx.AsyncClient,
    sigungu_cd: str,
    bjdong_cd: str,
    page_no: int,
    bun: str = "",
    ji: str = "",
) -> tuple[int, list[dict[str, str]]]:
    if not settings.data_go_kr_api_key:
        raise HTTPException(status_code=500, detail="DATA_GO_KR_API_KEY가 설정되지 않았습니다.")

    params = {
        "serviceKey": unquote(settings.data_go_kr_api_key),
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "platGbCd": "0",
        "numOfRows": _BUILDING_HUB_ROWS,
        "pageNo": page_no,
    }
    if bun:
        params["bun"] = bun
    if ji:
        params["ji"] = ji

    response = await client.get(
        _BUILDING_HUB_BASE_URL,
        params=params,
        timeout=20.0,
    )
    if response.status_code != 200:
        return 0, []

    root = ET.fromstring(response.text)
    # resultCode가 '00'이면 성공
    res_code = root.findtext(".//resultCode")
    if res_code not in ["00", "000"]:
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
    bun: str = "",
    ji: str = "",
) -> tuple[int, list[dict[str, str]]]:
    total_count, first_page_items = await _fetch_building_register_page(client, sigungu_cd, bjdong_cd, 1, bun, ji)
    if total_count <= len(first_page_items):
        return total_count, first_page_items

    total_pages = (total_count + _BUILDING_HUB_ROWS - 1) // _BUILDING_HUB_ROWS
    tasks = [
        _fetch_building_register_page(client, sigungu_cd, bjdong_cd, page_no, bun, ji)
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
        result = await _geocode_query(client, query)
    if not result:
        return {"result": None}
    return {"result": result}


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


@app.get("/listing-checks/search")
async def search_listing_for_checks(
    query: str = Query(..., description="지번 주소"),
    building_name: str | None = Query(None, description="선택된 건물명"),
    property_type: str = Query(default="apt", description="매물 종류: apt/offi/rh/sh"),
):
    if not settings.naver_maps_client_id or not settings.naver_maps_client_secret:
        raise HTTPException(status_code=500, detail="Naver Maps API 키가 설정되지 않았습니다.")
    if not settings.data_go_kr_api_key:
        raise HTTPException(status_code=500, detail="DATA_GO_KR_API_KEY가 설정되지 않았습니다.")
    if property_type not in _PROPERTY_TYPE_MAP:
        raise HTTPException(status_code=400, detail=f"알 수 없는 매물 종류: {property_type}")

    # 1. CSV 기반 법정동 코드 조회
    full_code = _lookup_legal_code(query.strip())
    if not full_code:
        # Fallback to Geocoding + Reverse Geocoding if CSV lookup fails
        async with httpx.AsyncClient() as client:
            geo = await _geocode_query(client, query.strip())
            if not geo:
                raise HTTPException(status_code=404, detail="주소 정보를 찾을 수 없습니다.")
            lat, lng = float(geo["y"]), float(geo["x"])
            location = await _reverse_geocode(client, lat, lng)
            sigungu_cd = location.get("sigungu_cd", "")
            bjdong_cd = location.get("bjdong_cd", "")
            full_code = sigungu_cd + bjdong_cd
    else:
        sigungu_cd = full_code[:5]
        bjdong_cd = full_code[5:]
        # 위경도는 지도 표시를 위해 필요하므로 Geocoding은 수행
        async with httpx.AsyncClient() as client:
            geo = await _geocode_query(client, query.strip())

    if not full_code or len(full_code) < 10:
        raise HTTPException(status_code=404, detail="법정동 코드를 찾지 못했습니다.")

    # 번지 정보 추출
    bun, ji = _extract_bun_ji(query.strip())

    async with httpx.AsyncClient() as client:
        # 2. 건축물대장 조회 (bun, ji 추가)
        total_count, items = await _fetch_building_register_items(client, sigungu_cd, bjdong_cd, bun, ji)
        
        candidates: list[dict[str, str]] = []
        if items:
            for item in items:
                if _is_matching_building(building_name, item.get("bldNm", "")):
                    candidates.append(item)
            
            # 지명으로 필터링된 결과가 없으면 해당 지번의 모든 건물을 보여줌
            if not candidates:
                candidates = items

            building_candidates = [_summarize_building_item(item) for item in candidates[:30]]
        else:
            building_candidates = []

        # 3. 실거래가 조회 (전세/매매 병렬 조회)
        deal_from, deal_to = _recent_12m_period()
        months = _iter_months(deal_from, deal_to)
        
        # 전세 API 설정
        r_svc, r_method, r_bld_f, r_area_f = _PROPERTY_TYPE_MAP[property_type]
        # 매매 API 설정
        t_svc, t_method, t_bld_f, t_area_f, t_price_f = _TRADE_TYPE_MAP[property_type]

        target_search_name = building_name.strip() if building_name else ""
        
        rent_tasks = [
            _fetch_month(client, r_svc, r_method, r_bld_f, r_area_f, sigungu_cd, ymd, "", target_search_name)
            for ymd in months
        ]
        trade_tasks = [
            _fetch_month(client, t_svc, t_method, t_bld_f, t_area_f, sigungu_cd, ymd, "", target_search_name, t_price_f)
            for ymd in months
        ]

        results = await asyncio.gather(*(rent_tasks + trade_tasks))
        
        # 전세/월세 데이터 처리 (월세 0인 전세만 필터링)
        all_rent_items = [item for month_items in results[:len(months)] for item in month_items]
        jeonse_items = [item for item in all_rent_items if _to_int(item.get("monthlyRent")) == 0]
        
        # 매매 데이터 처리 (시세용)
        trade_items = [item for month_items in results[len(months):] for item in month_items]
        
        # 시세 결정: 매매가 있으면 매매가 기준, 없으면 전세가 기준 (Mock 대비 실제 데이터 우선)
        market_price_krw = 0
        latest_trade = None
        if trade_items:
            market_price_krw, latest_trade = _pick_latest_market_price_krw(trade_items)
            price_source = "actual-trade-transaction"
        else:
            market_price_krw, latest_trade = _pick_latest_market_price_krw(jeonse_items)
            price_source = "latest-jeonse-transaction"

    return {
        "query": query.strip(),
        "property_type": property_type,
        "location": {
            "x": geo["x"] if geo else None,
            "y": geo["y"] if geo else None,
            "address": query.strip(),
        },
        "building": {
            "total_count": total_count,
            "matched_count": len(building_candidates),
            "selected": building_candidates[0] if building_candidates else None,
            "candidates": building_candidates,
        },
        "rent": {
            "deal_from": deal_from,
            "deal_to": deal_to,
            "total": len(jeonse_items),
            "items": sorted(jeonse_items, key=_extract_ymd, reverse=True),
        },
        "market_price": {
            "price_krw": market_price_krw,
            "source": price_source,
            "latest_trade": latest_trade,
        },
    }


_LAWD_CD_MAP: dict = json.loads(
    (Path(__file__).parent / "data" / "lawd_cd_map.json").read_text(encoding="utf-8")
)


_PROPERTY_TYPE_MAP = {
    # (서비스명, 메서드명, 건물명XML필드, 면적XML필드) - 전월세 전용
    "apt":  ("RTMSDataSvcAptRent",  "getRTMSDataSvcAptRent",  "aptNm",     "excluUseAr"),
    "offi": ("RTMSDataSvcOffiRent", "getRTMSDataSvcOffiRent", "offiNm",    "excluUseAr"),
    "rh":   ("RTMSDataSvcRHRent",   "getRTMSDataSvcRHRent",   "mhouseNm",  "excluUseAr"),
    "sh":   ("RTMSDataSvcSHRent",   "getRTMSDataSvcSHRent",   "houseType", "totalFloorAr"),
}

_TRADE_TYPE_MAP = {
    # (서비스명, 메서드명, 건물명XML필드, 면적XML필드, 가격필드) - 매매 전용
    "apt":  ("RTMSDataSvcAptTrade",  "getRTMSDataSvcAptTrade",  "aptNm",     "excluUseAr", "dealAmount"),
    "offi": ("RTMSDataSvcOffiTrade", "getRTMSDataSvcOffiTrade", "offiNm",    "excluUseAr", "dealAmount"),
    "rh":   ("RTMSDataSvcRHTrade",   "getRTMSDataSvcRHTrade",   "mhouseNm",  "excluUseAr", "dealAmount"),
    "sh":   ("RTMSDataSvcSHTrade",   "getRTMSDataSvcSHTrade",   "houseType", "totalFloorAr", "dealAmount"),
}


_RESIDENTIAL_USE_KEYWORDS = (
    "공동주택",
    "단독주택",
    "다가구",
    "다세대",
    "연립",
    "주택",
    "오피스텔",
)

_LISTING_CHECK_SYSTEM_PROMPT = """
너는 전세 매물 위험도를 분석하는 전문 AI 보조자다.
제공된 매물 정보를 바탕으로 종합적인 위험도 점검 리포트를 작성하라.

분석 원칙 (건축물대장 체크 가이드 반영):
1. 사용승인일: 건물의 노후도를 확인하고, 오래된 경우 유지보수 및 권리관계 리스크를 언급한다.
2. 건축물 용도: 주거용 여부를 확인하고, 근린생활시설 등 비주거용인 경우 임대차 보호법 적용 여부 및 위험성을 경고한다.
3. 구조와 층수: 구조가 복잡하거나 지하층이 있는 경우 누수, 환기, 관리 상태 확인을 권장한다.
4. 세대수/가구수: 세대수가 많으면 다수의 선순위 보증금 리스크(다가구의 경우 특히 중요)를 짚어준다.
5. 건축물 구분: 다가구와 다세대/아파트의 권리관계(개별 등기 여부) 차이에 따른 리스크를 분석한다.

분석 단계:
1. 제공된 5가지 핵심 정보(건물명, 시세, 최근 전세가, 위치, 건축물 정보)를 요약하여 명시한다.
2. 위 분석 원칙에 따라 건축물대장 정보와 전세가율(시세 대비 보증금)을 입체적으로 분석한다.
3. 발견된 위험 요소나 주의 사항을 사용자에게 친절하고 전문적인 어조로 설명한다.

출력 형식:
- 건물명: ...
- 시세(실거래가): ...
- 최근 전세가: ...
- 위치: ...
- 건축물 정보(건축물대장 정보)
(... 이제 분석 결과 ...)

작성 규칙:
- 핵심 결론을 먼저 제시한다.
- 법률적 단정보다는 위험 가능성을 언급하고, 등기부등본 확인 및 전문가 상담을 강력히 권장한다.
- 한국어로 명확하고 간결하게 6~10문장 내외로 작성한다.
""".strip()


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    text = str(value).replace(",", "").strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _to_krw_from_manwon(value: Any) -> int:
    return _to_int(value) * 10_000


def _extract_ymd(item: dict[str, Any]) -> int:
    year = str(item.get("dealYear") or "").strip()
    month = str(item.get("dealMonth") or "").strip().zfill(2)
    day = str(item.get("dealDay") or "").strip().zfill(2)
    if not year or not month or not day:
        return 0
    try:
        return int(f"{year}{month}{day}")
    except ValueError:
        return 0


def _pick_latest_market_price_krw(items: list[dict[str, Any]]) -> tuple[int, dict[str, Any] | None]:
    if not items:
        return 0, None
    latest = max(items, key=_extract_ymd)
    return _to_krw_from_manwon(latest.get("deposit")), latest


def _recent_12m_period() -> tuple[str, str]:
    today = date.today()
    end = f"{today.year}{str(today.month).zfill(2)}"
    start_year = today.year - 1 if today.month < 12 else today.year
    start_month = (today.month % 12) + 1
    start = f"{start_year}{str(start_month).zfill(2)}"
    return start, end


def _summarize_check_overall(checks: list[ListingCheckResult]) -> ListingCheckSummary:
    rank = {"fail": 3, "warn": 2, "unknown": 1, "pass": 0}
    overall = "pass"
    for check in checks:
        if rank[check.status] > rank[overall]:
            overall = check.status
    triggered = [check.code for check in checks if check.status != "pass"]
    return ListingCheckSummary(overall_status=overall, triggered_checks=triggered)


def _is_residential_use(building_type: str, detail_use: str) -> bool | None:
    text = f"{building_type} {detail_use}".strip()
    if not text:
        return None
    return any(keyword in text for keyword in _RESIDENTIAL_USE_KEYWORDS)


class MarketPriceProvider(Protocol):
    async def get_market_price_krw(self, payload: ListingCheckAnalyzeRequest) -> int:
        ...


class MockMarketPriceProvider:
    _MULTIPLIERS = {
        "apt": 1.35,
        "offi": 1.28,
        "rh": 1.22,
        "sh": 1.18,
    }

    async def get_market_price_krw(self, payload: ListingCheckAnalyzeRequest) -> int:
        if payload.market_price_krw and payload.market_price_krw > 0:
            return payload.market_price_krw

        recent_transactions = (payload.extra_signals or {}).get("recent_transactions") or []
        if isinstance(recent_transactions, list):
            recent_price, _ = _pick_latest_market_price_krw(recent_transactions)
            if recent_price > 0:
                return recent_price

        selected_deposit = _to_krw_from_manwon((payload.selected_rent_item or {}).get("deposit"))
        base = payload.deposit_krw or selected_deposit
        if base <= 0:
            return 0

        multiplier = self._MULTIPLIERS.get(payload.property_type, 1.3)
        return int(base * multiplier)


market_price_provider: MarketPriceProvider = MockMarketPriceProvider()


def _run_deposit_to_market_check(deposit_krw: int, market_price_krw: int) -> ListingCheckResult:
    if market_price_krw <= 0:
        return ListingCheckResult(
            code="deposit_to_market_ratio",
            title="주택 시세 대비 보증금",
            status="unknown",
            reason="시세 데이터를 확보하지 못해 전세가율을 계산할 수 없습니다.",
            evidence={"deposit_krw": deposit_krw, "market_price_krw": market_price_krw},
        )

    ratio = deposit_krw / market_price_krw
    status = "fail" if ratio > 0.8 else "pass"
    reason = (
        "보증금이 시세의 80%를 초과합니다."
        if status == "fail"
        else "보증금이 시세의 80% 이하입니다."
    )
    return ListingCheckResult(
        code="deposit_to_market_ratio",
        title="주택 시세 대비 보증금",
        status=status,
        reason=reason,
        evidence={
            "deposit_krw": deposit_krw,
            "market_price_krw": market_price_krw,
            "ratio": round(ratio, 4),
            "threshold": 0.8,
        },
    )


def _run_residential_use_check(selected_building: dict[str, Any]) -> ListingCheckResult:
    building_type = (selected_building.get("building_type") or "").strip()
    detail_use = (selected_building.get("detail_use") or "").strip()
    result = _is_residential_use(building_type, detail_use)

    if result is None:
        return ListingCheckResult(
            code="residential_use",
            title="건축물 용도(주거용 여부)",
            status="unknown",
            reason="건축물 용도 정보가 부족해 주거용 여부를 판단할 수 없습니다.",
            evidence={"building_type": building_type, "detail_use": detail_use},
        )

    if result:
        return ListingCheckResult(
            code="residential_use",
            title="건축물 용도(주거용 여부)",
            status="pass",
            reason="건축물 용도 정보에서 주거 관련 용도가 확인됩니다.",
            evidence={"building_type": building_type, "detail_use": detail_use},
        )

    return ListingCheckResult(
        code="residential_use",
        title="건축물 용도(주거용 여부)",
        status="fail",
        reason="건축물 용도가 주거용으로 확인되지 않습니다.",
        evidence={"building_type": building_type, "detail_use": detail_use},
    )


async def _generate_listing_check_explanation(
    payload: ListingCheckAnalyzeRequest,
    checks: list[ListingCheckResult],
    summary: ListingCheckSummary,
) -> str:
    if not settings.openai_api_key or not settings.openai_api_key.strip():
        return "규칙 기반 점검 결과입니다. OPENAI_API_KEY가 없어 자연어 설명은 기본 모드로 제공됩니다."

    model = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.1,
    )
    
    # 5가지 핵심 정보 구성
    context_data = {
        "1. 건물 이름": payload.selected_building.get("building_name", payload.listing_name),
        "2. 시세(실거래가)": f"{payload.market_price_krw:,}원" if payload.market_price_krw else "정보 없음",
        "3. 가장 최근 전세 거래내역": payload.selected_rent_item,
        "4. 위치(주소)": payload.selected_building.get("address", "정보 없음"),
        "5. 건축물대장 정보": {
            "용도": payload.selected_building.get("building_type"),
            "상세용도": payload.selected_building.get("detail_use"),
            "구조": payload.selected_building.get("structure"),
            "층수": payload.selected_building.get("floors"),
            "사용승인일": payload.selected_building.get("use_approval_date"),
        },
        "규칙 점검 결과": [check.model_dump() for check in checks],
        "종합 상태": summary.model_dump(),
    }

    messages = [
        SystemMessage(content=_LISTING_CHECK_SYSTEM_PROMPT),
        HumanMessage(content=f"다음 매물 정보를 분석하여 리포트를 작성해줘:\n\n{json.dumps(context_data, ensure_ascii=False, indent=2)}"),
    ]
    try:
        result = await asyncio.to_thread(model.invoke, messages)
        content = result.content if isinstance(result.content, str) else str(result.content)
        return content.strip() or "점검 결과를 분석했지만 설명 문장을 생성하지 못했습니다."
    except Exception as e:
        print(f"LLM Error: {e}")
        return "규칙 결과를 기반으로 점검을 완료했습니다. 모델 설명 생성 중 오류가 발생했습니다."


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


def _is_matching_building(search_name: str | None, target_name: str | None) -> bool:
    if not search_name:
        return True
    if not target_name:
        return False
    s = _normalize_text(search_name)
    t = _normalize_text(target_name)
    if s in t or t in s:
        return True
    # 앞 3글자 이상이 겹치면 매칭으로 간주 (블루시안아파트 vs 블루시안(101))
    common_len = min(len(s), len(t), 3)
    if common_len >= 2 and s[:common_len] == t[:common_len]:
        return True
    return False


async def _fetch_month(
    client: httpx.AsyncClient,
    svc_name: str,
    method_name: str,
    building_field: str,
    area_field: str,
    lawd_cd: str,
    ymd: str,
    dong: str,
    building_name: str,
    price_field: str = "deposit",
) -> list[dict]:
    url = (
        f"https://apis.data.go.kr/1613000/{svc_name}/{method_name}"
        f"?serviceKey={settings.data_go_kr_api_key}"
        f"&LAWD_CD={lawd_cd}&DEAL_YMD={ymd}&numOfRows=1000&pageNo=1"
    )
    response = await client.get(url, timeout=10.0)
    if response.status_code != 200:
        return []
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return []
    
    if root.findtext(".//resultCode") != "000":
        return []
    items = root.findall(".//item")
    result = []
    for item in items:
        if dong and dong not in (item.findtext("umdNm") or ""):
            continue
        current_building_name = item.findtext(building_field) or ""
        if building_name and not _is_matching_building(building_name, current_building_name):
            continue

        result.append({
            "buildingNm": current_building_name,
            "umdNm": item.findtext("umdNm"),
            "excluUseAr": item.findtext(area_field),
            "deposit": item.findtext(price_field), # Trade API의 경우 dealAmount가 들어옴
            "monthlyRent": item.findtext("monthlyRent") or "0",
            "floor": item.findtext("floor"),
            "contractType": item.findtext("contractType"),
            "dealYear": item.findtext("year") or item.findtext("dealYear"),
            "dealMonth": item.findtext("month") or item.findtext("dealMonth"),
            "dealDay": item.findtext("day") or item.findtext("dealDay"),
        })
    return result


@app.get("/jeonse-data")
async def get_jeonse_data(
    sido: str = Query(..., description="시도명 (예: 경기도)"),
    sigungu: str = Query(..., description="시군구명 (예: 수원시 권선구)"),
    dong: str = Query(default="", description="읍면동명 (예: 탑동, 생략 시 전체)"),
    building_name: str = Query(default="", description="매물명 필터 (부분일치, 선택)"),
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
        tasks = [
            _fetch_month(client, svc_name, method_name, building_field, area_field, lawd_cd, ymd, dong, building_name)
            for ymd in months
        ]
        results_per_month = await asyncio.gather(*tasks)

    result = [item for month_items in results_per_month for item in month_items]
    return {"lawd_cd": lawd_cd, "deal_from": deal_from, "deal_to": deal_to, "total": len(result), "items": result}


@app.post("/listing-checks/analyze", response_model=ListingCheckAnalyzeResponse)
async def analyze_listing_checks(payload: ListingCheckAnalyzeRequest) -> ListingCheckAnalyzeResponse:
    if payload.deposit_krw <= 0:
        raise HTTPException(status_code=400, detail="deposit_krw는 0보다 커야 합니다.")

    market_price_krw = await market_price_provider.get_market_price_krw(payload)
    checks = [
        _run_deposit_to_market_check(payload.deposit_krw, market_price_krw),
        _run_residential_use_check(payload.selected_building),
    ]
    summary = _summarize_check_overall(checks)
    explanation = await _generate_listing_check_explanation(payload, checks, summary)
    return ListingCheckAnalyzeResponse(
        checks=checks,
        summary=summary,
        llm_explanation=explanation,
    )


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
