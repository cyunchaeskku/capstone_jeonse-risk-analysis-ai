import asyncio
import csv
import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import date
from typing import Any, Protocol
from urllib.parse import unquote
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import get_current_user, get_optional_user, router as auth_router
from .chatbot import ChatbotService
from .db import get_db
from .models import Analysis, User
from .building_register_inspector import inspect_building_register_pdf
from .registry_inspector import inspect_registry_text
from .registry_parser import parse_registry_pdf
from .schemas import (
    AnalysisDetailResponse,
    AnalysisListItem,
    AnalysisRecordResponse,
    HealthResponse,
    ListingCheckAnalyzeRequest,
    ListingCheckAnalyzeResponse,
    ListingCheckResult,
    ListingCheckSummary,
    QaRequest,
    RegistryInspectResponse,
    RegistryMaxClaimItem,
    MortgageItem,
    RegistryParseResponse,
    RiskAssessRequest,
    RiskAssessResponse,
    RiskFactor,
    RootResponse,
)
from .settings import settings


logger = logging.getLogger("uvicorn.error")

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

app.include_router(auth_router)

chatbot_service = ChatbotService()

_CSV_PATH = Path(__file__).parent.parent.parent / "data" / "address_code.csv"
def _load_legal_code_map():
    mapping = {}
    if not _CSV_PATH.exists():
        return mapping
    try:
        # BOM이 붙은 CSV라 utf-8로 열면 첫 컬럼명이 "\ufeff법정동코드"가 되어 매핑이 전부 비어버린다.
        with open(_CSV_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("삭제일자") and row["삭제일자"].strip():
                    continue
                sido = (row.get("시도명") or "").strip()
                sig = (row.get("시군구명") or "").strip()
                eup = (row.get("읍면동명") or "").strip()
                code = (row.get("법정동코드") or "").strip()
                if code:
                    # CSV는 "수원시권선구"처럼 붙여 쓰는데 주소 문자열은 "수원시 권선구"로 띄운다.
                    # 공백을 없앤 형태로 저장해 양쪽을 맞춘다.
                    mapping[(sido, sig.replace(" ", ""), eup)] = code
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
        sig = "".join(words[1:i])
        key = (sido, sig, eup)
        if key in _CSV_LEGAL_CODE_MAP:
            return _CSV_LEGAL_CODE_MAP[key]

    return None

_BUILDING_HUB_BASE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
_BUILDING_HUB_ROWS = 1000


class UpstreamUnavailable(HTTPException):
    """외부 API 장애 → 502. 500이면 우리 서버 버그로 읽힌다.

    미처리 예외는 CORSMiddleware 바깥에서 응답이 만들어져 CORS 헤더가 빠진다 →
    브라우저가 네트워크 오류로 처리 → 프론트가 원인을 "서버 연결 불가"로 오표시.
    """

    def __init__(self, api_name: str) -> None:
        super().__init__(
            status_code=502,
            detail=f"{api_name} 연동에 실패했습니다. 해당 기관 API가 응답하지 않아 잠시 후 다시 시도해 주세요.",
        )


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


async def _search_place_items(client: httpx.AsyncClient, query: str) -> list[dict[str, str]]:
    """네이버 지역검색. 상호명 기반이라 지번·도로명만 넣으면 빈 결과가 온다."""
    if not settings.naver_search_client_id or not settings.naver_search_client_secret:
        raise HTTPException(status_code=500, detail="Naver Search API 키가 설정되지 않았습니다.")

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

    return [
        {
            "title": _remove_tags(item.get("title", "")),
            "roadAddress": item.get("roadAddress", ""),
            "address": item.get("address", ""),
            "category": item.get("category", ""),
            "mapx": item.get("mapx", ""),
            "mapy": item.get("mapy", ""),
        }
        for item in response.json().get("items", [])
    ]


@app.get("/places/search")
async def search_places(query: str = Query(..., description="검색할 장소명")):
    async with httpx.AsyncClient() as client:
        return {"items": await _search_place_items(client, query)}


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


def _extract_dong_and_jibun(address_str: str) -> tuple[str, str]:
    words = address_str.strip().split()
    dong = next((word for word in words if word.endswith(("동", "읍", "면"))), "")
    match = re.search(r"(\d+(?:-\d+)?)$", address_str)
    return dong, match.group(1) if match else ""


def _is_matching_rh_address(target_dong: str, target_jibun: str, item_dong: str | None, item_jibun: str | None) -> bool:
    return bool(target_dong and target_jibun) and (item_dong or "").strip() == target_dong and (item_jibun or "").strip() == target_jibun


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

    try:
        response = await client.get(
            _BUILDING_HUB_BASE_URL,
            params=params,
            timeout=20.0,
        )
    except httpx.RequestError as exc:
        logger.warning("건축물대장 API 연결 실패: %s", type(exc).__name__)
        raise UpstreamUnavailable("건축물대장(국토교통부)") from exc
    if response.status_code != 200:
        return 0, []

    content_type = response.headers.get("content-type", "").lower()
    if "json" in content_type:
        try:
            payload = response.json()
        except ValueError:
            logger.warning("건축물대장 API JSON 응답을 읽지 못했습니다: body=%r", response.text[:200])
            return 0, []

        if payload.get("header", {}).get("resultCode") not in ["00", "000"]:
            return 0, []

        body = payload.get("body", {})
        raw_items = body.get("items", {}).get("item", [])
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        items = [
            {key: str(value or "") for key, value in item.items()}
            for item in raw_items
            if isinstance(item, dict)
        ]
        return int(body.get("totalCount") or len(items)), items

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        logger.warning(
            "건축물대장 API 응답이 XML이 아닙니다: status=%s, content_type=%s, body=%r",
            response.status_code,
            response.headers.get("content-type"),
            response.text[:200],
        )
        return 0, []
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


def _registry_max_claim_items(result) -> list[RegistryMaxClaimItem]:
    return [
        RegistryMaxClaimItem(
            amount_krw=item.amount_krw,
            raw_text=item.raw_text,
            page=item.page,
            collateral_list_no=item.collateral_list_no,
            shared_property_count=item.shared_property_count,
        )
        for item in result.max_claim_amounts
    ]


@app.post("/registry/parse", response_model=RegistryParseResponse)
async def parse_registry_document(file: UploadFile = File(...)) -> RegistryParseResponse:
    filename = file.filename or "registry.pdf"
    if file.content_type and file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="빈 PDF 파일입니다.")

    result = parse_registry_pdf(pdf_bytes)
    if result.max_claim_amount_krw is None:
        return RegistryParseResponse(
            filename=filename,
            max_claim_amount_krw=None,
            max_claim_amounts=[],
            status="needs_review",
            message="등기부등본에서 채권최고액을 찾지 못했습니다.",
        )

    return RegistryParseResponse(
        filename=filename,
        max_claim_amount_krw=result.max_claim_amount_krw,
        max_claim_amounts=_registry_max_claim_items(result),
        status="parsed",
        message="채권최고액을 추출했습니다.",
    )


@app.post("/building-register/inspect")
async def inspect_building_register(file: UploadFile = File(...)) -> dict[str, Any]:
    """건축물대장 PDF를 비전 모델로 판독한다. 위반건축물 표시(R6) 확보가 목적이다."""
    filename = file.filename or "building_register.pdf"
    if (file.content_type and file.content_type != "application/pdf") or not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="빈 PDF 파일입니다.")

    try:
        inspection = inspect_building_register_pdf(pdf_bytes)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return {"file_name": filename, "inspection": inspection}


def _attach_shared_collateral_counts(
    inspection: dict[str, Any],
    max_claim_items: list[RegistryMaxClaimItem],
) -> None:
    """LLM이 뽑은 근저당 항목에 파서가 센 공동담보 물건 수를 붙인다.

    말소 여부는 LLM만 알고, 공동담보 물건 수는 파서만 안다. R2 비례배분에는 둘 다
    필요하므로 채권최고액 금액을 열쇠로 이어 붙인다.
    """
    counts = {item.amount_krw: item.shared_property_count for item in max_claim_items}
    mortgages = (inspection.get("rights_section") or {}).get("mortgages")
    if not isinstance(mortgages, list):
        return
    for mortgage in mortgages:
        if not isinstance(mortgage, dict):
            continue
        try:
            amount = int(str(mortgage.get("amount_krw") or 0).replace(",", ""))
        except ValueError:
            amount = 0
        mortgage["shared_property_count"] = counts.get(amount, 1)


@app.post("/registry/inspect", response_model=RegistryInspectResponse)
async def inspect_registry_document(file: UploadFile = File(...)) -> RegistryInspectResponse:
    filename = file.filename or "registry.pdf"
    if file.content_type and file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="빈 PDF 파일입니다.")

    result = parse_registry_pdf(pdf_bytes)
    try:
        max_claim_items = _registry_max_claim_items(result)
        inspection = inspect_registry_text(
            result.text,
            max_claim_amounts=[item.model_dump() for item in max_claim_items],
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "REGISTRY_INSPECTOR_NOT_CONFIGURED",
                "message": str(error),
                "action_hint": "OPENAI_API_KEY를 설정한 뒤 서버를 다시 시작하세요.",
            },
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "REGISTRY_INSPECTION_FAILED",
                "message": "등기부등본 특이사항 추출 중 오류가 발생했습니다.",
                "action_hint": "잠시 후 다시 시도하거나 원문을 직접 확인하세요.",
            },
        ) from error

    _attach_shared_collateral_counts(inspection, max_claim_items)

    return RegistryInspectResponse(
        filename=filename,
        max_claim_amount_krw=result.max_claim_amount_krw,
        max_claim_amounts=max_claim_items,
        inspection=inspection,
        status="needs_review" if inspection.get("needs_human_review") else "inspected",
        message="등기부등본 특이사항을 추출했습니다.",
    )


@app.get("/analyses", response_model=list[AnalysisListItem])
def list_analyses(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[AnalysisListItem]:
    rows = db.scalars(
        select(Analysis)
        .where(Analysis.user_id == user.id)
        .order_by(Analysis.created_at.desc())
        .limit(50)
    ).all()
    return [
        AnalysisListItem(
            analysis_id=row.id,
            listing_name=row.listing_name,
            deposit_krw=row.deposit_krw,
            risk_grade=row.risk_grade,
            risk_score=row.risk_score,
            created_at=row.created_at,
        )
        for row in rows
    ]


@app.get("/analyses/{analysis_id}", response_model=AnalysisRecordResponse)
def get_analysis(
    analysis_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisRecordResponse:
    row = db.get(Analysis, analysis_id)
    # 남의 기록과 익명 기록은 존재 자체를 알리지 않는다.
    if row is None or row.user_id != user.id:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ANALYSIS_NOT_FOUND",
                "message": "해당 분석 기록을 찾을 수 없습니다.",
                "action_hint": "기록 목록에서 다시 선택하거나 새 분석을 실행하세요.",
            },
        )
    return AnalysisRecordResponse(
        analysis_id=row.id,
        listing_name=row.listing_name,
        created_at=row.created_at,
        request=row.request,
        result=row.result,
    )


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


# ---------------------------------------------------------------------------
# 공시가격 기반 시세 — HUG 주택가격 산정 사다리 ② 단계
# 실거래가가 없는 건물(통건물·거래 희소 다세대)의 시세를 여기서 확보한다.
# ---------------------------------------------------------------------------

_VWORLD_APART_PRICE_URL = "https://api.vworld.kr/ned/data/getApartHousingPriceAttr"
# HUG가 실거래가 부재 시 적용하는 공시가격 배율.
_OFFICIAL_PRICE_MULTIPLIER = 1.4


def _build_pnu(address_str: str) -> str | None:
    """지번 주소 -> PNU 19자리 (법정동코드10 + 대장구분1 + 본번4 + 부번4)."""
    legal_code = _lookup_legal_code(address_str)
    if not legal_code or len(legal_code) < 10:
        return None
    bun, ji = _extract_bun_ji(address_str)
    if not bun:
        return None
    parts = address_str.strip().split()
    # 산번지는 대장구분 2. 지번 토큰만 보고 판단해야 "부산"·"산본동" 같은 지명에 걸리지 않는다.
    is_mountain = parts[-1].startswith("산") or (len(parts) >= 2 and parts[-2] == "산")
    # _extract_bun_ji는 부번이 없으면 ""를 주는데 PNU에서는 "0000"으로 채워야 한다.
    return f"{legal_code[:10]}{'2' if is_mountain else '1'}{bun}{(ji or '').zfill(4)}"


# 한 번에 받아올 최대 행 수. 대단지는 이걸 넘겨 잘리므로 dongNm/hoNm으로 좁혀야 한다.
_VWORLD_MAX_ROWS = 1000


async def _fetch_official_price_units(
    client: httpx.AsyncClient,
    pnu: str,
    stdr_year: str,
    dong: str | None = None,
    ho: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """PNU의 공동주택 공시가격을 세대 단위로 조회한다.

    (세대 목록, 잘림 여부)를 돌려준다. 공시가격 대상이 아니면 빈 목록.
    은마아파트처럼 PNU 하나에 수천 세대가 묶인 단지는 dongNm/hoNm을 함께 보내
    서버에서 좁혀야 한다. 안 그러면 상한에 걸려 사용자의 세대가 조용히 빠진다.
    """
    if not settings.vworld_api_key:
        return [], False
    params: dict[str, Any] = {
        "key": settings.vworld_api_key,
        # domain 누락 시 키가 맞아도 INCORRECT_KEY로 거부된다.
        "domain": settings.vworld_api_domain,
        "pnu": pnu,
        "format": "xml",
        "stdrYear": stdr_year,
        "numOfRows": _VWORLD_MAX_ROWS,
        "pageNo": 1,
    }
    if dong:
        params["dongNm"] = dong
    if ho:
        params["hoNm"] = ho
    try:
        response = await client.get(_VWORLD_APART_PRICE_URL, params=params, timeout=20)
        root = ET.fromstring(response.text)
    except (httpx.HTTPError, ET.ParseError) as exc:
        logger.warning("공시가격 조회 실패 pnu=%s: %s", pnu, type(exc).__name__)
        return [], False

    units: dict[tuple[str, str], dict[str, Any]] = {}
    for field in root.findall(".//field"):
        def text(tag: str) -> str:
            return (field.findtext(tag) or "").strip()

        # stdrYear 필터를 걸어도 다른 연도가 섞여 오는 경우가 있어 행 단위로 다시 확인한다.
        if text("stdrYear") != stdr_year:
            continue
        official_price = _to_int(text("pblntfPc"))
        if official_price <= 0:
            continue
        dong, ho = text("dongNm"), text("hoNm")
        # 같은 세대가 두 행씩 중복으로 내려온다(파크뷰 28세대 -> 56행). 값은 동일하다.
        units.setdefault((dong, ho), {
            "dong": dong,
            "ho": ho,
            "floor": text("floorNm"),
            "area_m2": float(text("prvuseAr") or 0),
            "building_name": text("aphusNm"),
            "building_kind": text("aphusSeCodeNm"),
            "official_price_krw": official_price,
            "estimated_price_krw": int(official_price * _OFFICIAL_PRICE_MULTIPLIER),
            "stdr_year": text("stdrYear"),
        })

    row_count = len(root.findall(".//field"))
    return (
        sorted(units.values(), key=lambda u: (u["dong"], _to_int(u["ho"]), u["ho"])),
        row_count >= _VWORLD_MAX_ROWS,
    )


_VWORLD_ADDRESS_URL = "https://api.vworld.kr/req/address"


# "…로 6", "…3길 12-3"처럼 도로명+건물번호로 끝나는 형태만 통과시킨다.
# VWorld 지오코더는 아무 문자열이나 억지로 매칭시켜서("은마아파트" -> 창원시 구암동)
# 이 가드가 없으면 엉뚱한 지번이 조용히 들어온다.
_ROAD_ADDRESS_RE = re.compile(r"(로|길)\s*\d+(-\d+)?\s*$")


def _looks_like_road_address(address: str) -> bool:
    return bool(_ROAD_ADDRESS_RE.search(address.strip()))


async def _road_address_to_parcel(client: httpx.AsyncClient, address: str) -> str | None:
    """도로명주소 -> 지번주소. 좌표를 거쳐 변환한다(getcoord ROAD -> getAddress PARCEL)."""
    if not settings.vworld_api_key:
        return None
    common = {"service": "address", "version": "2.0", "crs": "EPSG:4326",
              "key": settings.vworld_api_key, "format": "json"}
    try:
        coord = await client.get(_VWORLD_ADDRESS_URL, params={
            **common, "request": "getcoord", "address": address, "type": "ROAD",
        }, timeout=20)
        payload = coord.json().get("response", {})
        if payload.get("status") != "OK":
            return None
        point = payload["result"]["point"]

        parcel = await client.get(_VWORLD_ADDRESS_URL, params={
            **common, "request": "getAddress",
            "point": f"{point['x']},{point['y']}", "type": "PARCEL",
        }, timeout=20)
        payload = parcel.json().get("response", {})
        if payload.get("status") != "OK":
            return None
        return (payload["result"][0].get("text") or "").strip() or None
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        logger.warning("도로명→지번 변환 실패 address=%s: %s", address, type(exc).__name__)
        return None


@app.get("/addresses/resolve")
async def resolve_address(query: str = Query(..., description="지번·도로명·건물명 아무거나")):
    """입력 문자열을 지번 후보로 바꾼다.

    네이버 지역검색은 상호명 기반이라 주소를 넣으면 0건이 나온다.
    그래서 지번이면 그대로 쓰고, 도로명이면 좌표를 거쳐 지번으로 바꾸고,
    둘 다 아닐 때만 장소 검색으로 넘긴다.
    """
    text = query.strip()
    if not text:
        raise HTTPException(status_code=400, detail="검색어가 비어 있습니다.")

    # ① 이미 지번이면 더 물을 게 없다. PNU가 만들어진다는 게 곧 지번이라는 증거다.
    if _build_pnu(text):
        return {"resolved_by": "jibun", "items": [{"title": text, "address": text, "roadAddress": ""}]}

    async with httpx.AsyncClient() as client:
        # ② 도로명 형태일 때만 지번으로 변환한다.
        if _looks_like_road_address(text):
            parcel = await _road_address_to_parcel(client, text)
            if parcel and _build_pnu(parcel):
                return {"resolved_by": "road", "items": [{"title": parcel, "address": parcel, "roadAddress": text}]}

        # ③ 건물명·상호명은 장소 검색으로
        items = [item for item in await _search_place_items(client, text) if item.get("address")]
        return {"resolved_by": "place", "items": items}


@app.get("/listing-checks/search")
async def search_listing_for_checks(
    query: str = Query(..., description="지번 주소"),
    building_name: str | None = Query(None, description="선택된 건물명"),
    property_type: str = Query(default="apt", description="매물 종류: apt/offi/rh/sh"),
    dong: str | None = Query(None, description="공시가격 조회용 동 이름"),
    ho: str | None = Query(None, description="공시가격 조회용 호수"),
    debug: bool = Query(default=False, description="개발용 원본 거래 진단 포함"),
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

        # 3. 실거래가 조회 (전월세 3년 / 매매 1년 병렬 조회)
        deal_from, deal_to = _recent_12m_period()
        rent_deal_from, _ = _recent_36m_period()
        rent_months = _iter_months(rent_deal_from, deal_to)
        trade_months = _iter_months(deal_from, deal_to)
        
        # 전세 API 설정
        r_svc, r_method, r_bld_f, r_area_f = _PROPERTY_TYPE_MAP[property_type]
        # 매매 API 설정
        t_svc, t_method, t_bld_f, t_area_f, t_price_f = _TRADE_TYPE_MAP[property_type]

        target_search_name = building_name.strip() if building_name else ""
        target_dong, target_jibun = _extract_dong_and_jibun(query)
        rh_dong, rh_jibun = (target_dong, target_jibun) if property_type == "rh" else ("", "")
        match_label = "동·지번 일치" if property_type == "rh" else "건물명 일치"
        rent_diagnostics: dict[str, Any] = {"raw_transactions": [], "errors": []} if debug else {}
        trade_diagnostics: dict[str, Any] = {"raw_transactions": [], "errors": []} if debug else {}

        rent_tasks = [
            _fetch_month(client, r_svc, r_method, r_bld_f, r_area_f, sigungu_cd, ymd, "", target_search_name, diagnostics=rent_diagnostics, rh_dong=rh_dong, rh_jibun=rh_jibun, debug_dong=target_dong)
            for ymd in rent_months
        ]
        trade_tasks = [
            _fetch_month(client, t_svc, t_method, t_bld_f, t_area_f, sigungu_cd, ymd, "", target_search_name, t_price_f, trade_diagnostics, rh_dong=rh_dong, rh_jibun=rh_jibun, debug_dong=target_dong)
            for ymd in trade_months
        ]

        results = await asyncio.gather(*(rent_tasks + trade_tasks))
        
        # 전세/월세 데이터 처리
        all_rent_items = [item for month_items in results[:len(rent_months)] for item in month_items]
        # 매매 데이터 처리 (시세용)
        trade_items = [item for month_items in results[len(rent_months):] for item in month_items]

        needs_trade_fallback = property_type == "rh" and not trade_items
        if needs_trade_fallback:
            fallback_from, fallback_to = _previous_12m_period(deal_from)
            fallback_months = _iter_months(fallback_from, fallback_to)
            fallback_results = await asyncio.gather(*(
                _fetch_month(client, t_svc, t_method, t_bld_f, t_area_f, sigungu_cd, ymd, "", target_search_name, t_price_f, trade_diagnostics, rh_dong=rh_dong, rh_jibun=rh_jibun, debug_dong=target_dong)
                for ymd in fallback_months
            ))
            trade_items = [item for month_items in fallback_results for item in month_items]

        jeonse_items = [item for item in all_rent_items if _to_int(item.get("monthlyRent")) == 0]
        latest_rent_price_krw, latest_rent = _pick_latest_market_price_krw(all_rent_items)

        # 시세 사다리 (HUG 주택가격 산정 순서)
        #   ① 해당 건물 매매 실거래가 → ② 공시가격 × 140% → ③ unknown
        # 전세 보증금을 시세로 대체하면 전세가율이 "보증금/보증금"이 되어 규칙이 무력화되므로
        # 절대 fallback으로 쓰지 않는다.
        market_price_krw = 0
        latest_trade = None
        price_source = "unavailable"
        if trade_items:
            market_price_krw, latest_trade = _pick_latest_market_price_krw(trade_items)
            price_source = "actual-trade-transaction"

        pnu = _build_pnu(query.strip())
        official_units: list[dict[str, Any]] = []
        official_selected: dict[str, Any] | None = None
        official_truncated = False
        if pnu:
            official_units, official_truncated = await _fetch_official_price_units(
                client, pnu, str(date.today().year), dong=dong, ho=ho
            )
            # 동·호수를 주면 API가 서버에서 좁혀주므로 남은 게 곧 사용자의 세대다.
            if (dong or ho) and len(official_units) == 1:
                official_selected = official_units[0]
            elif not dong and not ho and len(official_units) == 1:
                official_selected = official_units[0]

        if market_price_krw <= 0 and official_selected:
            market_price_krw = official_selected["estimated_price_krw"]
            price_source = "official-price-x140"

        if latest_rent:
            logger.info(
                "전월세 거래 검색 결과\n  건물명: %s\n  지번: %s\n  거래 수: %d건\n  최근 거래: %s\n  보증금: %s원",
                target_search_name,
                rh_jibun or "-",
                len(all_rent_items),
                _format_transaction_details(latest_rent),
                f"{latest_rent_price_krw:,}",
            )
        else:
            logger.info("전월세 거래 검색 결과\n  건물명: %s\n  지번: %s\n  거래 수: 0건\n  최근 전월세: 정보 없음", target_search_name, rh_jibun or "-")
            logger.info(
                "전월세 거래 0건 진단\n  API 원본 거래: %d건\n  %s: %d건\n  XML 파싱 실패: %d건\n  HTTP 오류: %d건\n  요청 오류: %d건",
                rent_diagnostics.get("api_item_count", 0),
                match_label,
                rent_diagnostics.get("building_match_count", 0),
                rent_diagnostics.get("non_xml_response_count", 0),
                rent_diagnostics.get("http_error_count", 0),
                rent_diagnostics.get("request_error_count", 0),
            )
        if latest_trade:
            logger.info(
                "시세 검색 결과\n  건물명: %s\n  지번: %s\n  기준: %s\n  매매 거래 수: %d건\n  최근 거래: %s\n  시세: %s원",
                target_search_name,
                rh_jibun or "-",
                price_source,
                len(trade_items),
                _format_transaction_details(latest_trade),
                f"{market_price_krw:,}",
            )
        else:
            logger.info("시세 검색 결과\n  건물명: %s\n  지번: %s\n  매매 거래 수: 0건\n  시세: 정보 없음", target_search_name, rh_jibun or "-")
            logger.info(
                "시세 0건 진단\n  API 원본 거래: %d건\n  %s: %d건\n  XML 파싱 실패: %d건\n  HTTP 오류: %d건\n  요청 오류: %d건",
                trade_diagnostics.get("api_item_count", 0),
                match_label,
                trade_diagnostics.get("building_match_count", 0),
                trade_diagnostics.get("non_xml_response_count", 0),
                trade_diagnostics.get("http_error_count", 0),
                trade_diagnostics.get("request_error_count", 0),
            )

    rent_request_count = rent_diagnostics.get("request_count", 0)
    rent_success_count = rent_diagnostics.get("success_count", 0)
    rent_lookup_status = (
        "complete"
        if rent_request_count > 0 and rent_success_count == rent_request_count
        else ("partial" if rent_success_count > 0 else "unavailable")
    )
    selected_building = building_candidates[0] if building_candidates else None
    concentration = _calculate_jeonse_concentration(
        all_rent_items,
        _to_int((selected_building or {}).get("households")),
        rent_deal_from,
        deal_to,
    )

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
            "selected": selected_building,
            "candidates": building_candidates,
        },
        "rent": {
            "deal_from": rent_deal_from,
            "deal_to": deal_to,
            "lookup_status": rent_lookup_status,
            "concentration": concentration,
            "total": len(all_rent_items),
            "items": sorted(all_rent_items, key=_extract_ymd, reverse=True),
        },
        "market_price": {
            "price_krw": market_price_krw,
            "source": price_source,
            "latest_trade": latest_trade,
        },
        "official_price": {
            "pnu": pnu,
            # 세대가 여럿인데 아직 못 고른 상태면 프론트가 선택 UI를 띄워야 한다.
            "needs_unit_selection": bool(official_units) and official_selected is None,
            "truncated": official_truncated,
            "selected": official_selected,
            "units": official_units,
        },
        **({
            "debug": {
                "period": {"from": deal_from, "to": deal_to},
                "rent": rent_diagnostics,
                "trade": trade_diagnostics,
            }
        } if debug else {}),
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

_RISK_ASSESSMENT_SYSTEM_PROMPT = """
너는 전세 계약 전 위험도 점검 결과를 설명하는 전문 AI 보조자다.
제공된 점검 결과만 근거로 설명하며, 규칙이 계산한 위험 점수·등급·통과/주의/위험 판정을 바꾸지 않는다.
입력에 없는 수치, 등기 내용, 법률 사실을 만들지 않는다. 데이터가 부족하거나 확인할 수 없는 항목은 그 불확실성을 명시한다.

답변은 한국어 Markdown으로 다음 순서로 작성한다.

## 핵심 결론

종합 위험 등급과 가장 중요한 이유를 2~3문장으로 설명한다.

## 주요 근거

- 각 위험·주의·확인 불가 항목을 점검 결과의 수치와 함께 설명한다.

## 계약 전 확인 사항

1. 계약 전에 확인하거나 조치할 항목을 우선순위대로 적는다.

제목은 반드시 독립된 줄에 쓰고, 제목 앞뒤에는 빈 줄을 둔다. 목록의 각 항목도 반드시 새 줄에서 시작한다.
법률적 결론을 단정하지 말고, 필요하면 최신 등기부등본 확인과 전문가 상담을 권한다.
""".strip()

_RISK_ASSESSMENT_MODEL = "gpt-5.6-terra"
_RISK_ASSESSMENT_REASONING_EFFORT = "medium"


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


def _format_transaction_details(item: dict[str, Any]) -> str:
    year = str(item.get("dealYear") or "").strip()
    month = str(item.get("dealMonth") or "").strip().zfill(2)
    day = str(item.get("dealDay") or "").strip().zfill(2)
    details = [f"{year}-{month}-{day}" if year and month and day else "날짜 정보 없음"]
    if item.get("floor"):
        details.append(f"{item['floor']}층")
    if item.get("excluUseAr"):
        details.append(f"{item['excluUseAr']}㎡")
    if item.get("contractType"):
        details.append(str(item["contractType"]))
    return " · ".join(details)


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


def _recent_36m_period() -> tuple[str, str]:
    today = date.today()
    end = f"{today.year}{today.month:02d}"
    start_index = today.year * 12 + today.month - 36
    start_year, start_month_index = divmod(start_index, 12)
    return f"{start_year}{start_month_index + 1:02d}", end


def _previous_12m_period(start: str) -> tuple[str, str]:
    year, month = int(start[:4]), int(start[4:])
    end_year, end_month = (year, month - 1) if month > 1 else (year - 1, 12)
    return f"{year - 1}{month:02d}", f"{end_year}{end_month:02d}"


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


def _run_deposit_to_market_check(
    deposit_krw: int, market_price_krw: int, registry_type: str
) -> ListingCheckResult:
    # 다가구: 시세는 건물 전체, 보증금은 한 호실 → 비율이 구조적으로 낮아 항상 pass. 판정은 R8이 맡는다.
    if registry_type == "general_building":
        return ListingCheckResult(
            code="deposit_to_market_ratio",
            title="주택 시세 대비 보증금",
            status="unknown",
            reason="다가구·단독주택은 시세가 건물 전체 기준이라 내 보증금만으로는 전세가율을 판정할 수 없습니다. 선순위 보증금을 합산한 부담률로 판정합니다.",
            evidence={
                "deposit_krw": deposit_krw,
                "market_price_krw": market_price_krw,
                "registry_type": registry_type,
            },
        )

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


_CHECK_WEIGHTS: dict[str, int] = {
    "deposit_to_market_ratio": 15,
    "residential_use": 15,
    "duplicate_contract": 25,
    "mortgage_ratio": 30,
    "owner_mismatch": 15,
    "rights_encumbrance": 30,
    "illegal_building": 15,
    "senior_deposit": 30,  # R2와 §1의 동일 부등식 → 동일 가중치
}

_RISK_SCORE_MAX = 100
_PROP_FLOOR = 0.6  # 비례 배점 시작. 이하는 0점
_PROP_CEIL = 1.0  # 시세 전액. 이상은 만점
_BURDEN_CODES = ("deposit_to_market_ratio", "mortgage_ratio", "senior_deposit")
_UNKNOWN_FLOOR_SCORE = 15  # 담보 여력을 하나도 못 본 경우의 바닥 점수
_COMBINED_OVERRIDE_THRESHOLD = 0.9  # R2-b 고위험 오버라이드
_RISK_SCORE_RANGES = (
    {"min_score": 0, "max_score": 14, "grade": "safe"},
    {"min_score": 15, "max_score": 29, "grade": "caution"},
    {"min_score": 30, "max_score": 59, "grade": "risk"},
    {"min_score": 60, "max_score": 100, "grade": "high_risk"},
)


def _proportional_points(ratio: float, weight: int) -> int:
    """부담률을 60%~100% 구간에서 선형 배점. 계단식 임계의 절벽·포화를 없앤다."""
    if ratio <= _PROP_FLOOR:
        return 0
    if ratio >= _PROP_CEIL:
        return weight
    return round(weight * (ratio - _PROP_FLOOR) / (_PROP_CEIL - _PROP_FLOOR))


def _stepwise_points(status: str, weight: int) -> int:
    if status == "fail":
        return weight
    if status == "warn":
        return weight // 2
    return 0


def _score_impact(check: ListingCheckResult) -> int:
    """§1 핵심 부등식을 쓰는 R1·R2-b는 비례 배점, 나머지는 계단 배점."""
    weight = _CHECK_WEIGHTS.get(check.code, 0)
    evidence = check.evidence or {}

    if check.code == "deposit_to_market_ratio":
        ratio = evidence.get("ratio")
        return _proportional_points(ratio, weight) if ratio is not None else 0

    if check.code == "mortgage_ratio":
        combined, alone = evidence.get("combined_ratio"), evidence.get("ratio")
        if combined is None:
            return _stepwise_points(check.status, weight)
        # R2-a(근저당 단독)는 계단 유지. combined로 갈음하면 보증금이 작은 고근저당 물건이 저평가된다.
        alone_status = (
            "fail"
            if alone > evidence["threshold_fail"]
            else "warn"
            if alone > evidence["threshold_warn"]
            else "pass"
        )
        return max(
            _stepwise_points(alone_status, weight), _proportional_points(combined, weight)
        )

    return _stepwise_points(check.status, weight)


def _build_score_breakdown(checks: list[ListingCheckResult]) -> list[dict[str, int | str]]:
    return [
        {
            "code": check.code,
            "max_points": _CHECK_WEIGHTS.get(check.code, 0),
            "added_points": _score_impact(check),
        }
        for check in checks
    ]


def _compute_risk_score(checks: list[ListingCheckResult]) -> int:
    score = min(sum(_score_impact(check) for check in checks), _RISK_SCORE_MAX)
    # §0-2. 담보 여력을 하나도 확인하지 못했으면 '안전'이라고 말하지 않는다.
    by_code = {check.code: check.status for check in checks}
    if all(by_code.get(code) == "unknown" for code in _BURDEN_CODES):
        return max(score, _UNKNOWN_FLOOR_SCORE)
    return score


def _calculate_jeonse_concentration(
    transactions: list[dict],
    households: int,
    period_from: str,
    period_to: str,
) -> dict[str, Any]:
    pure_jeonse = [item for item in transactions if _to_int(item.get("monthlyRent")) == 0]
    renewals = [item for item in pure_jeonse if str(item.get("contractType") or "").strip() == "갱신"]
    eligible = [item for item in pure_jeonse if str(item.get("contractType") or "").strip() != "갱신"]

    months = _iter_months(period_from, period_to)
    eligible_months = [
        f"{_to_int(item.get('dealYear')):04d}{_to_int(item.get('dealMonth')):02d}"
        for item in eligible
        if _to_int(item.get("dealYear")) > 0 and _to_int(item.get("dealMonth")) > 0
    ]
    peak_count = 0
    peak_from = months[-12] if len(months) >= 12 else period_from
    peak_to = months[-1] if months else period_to
    for index in range(max(1, len(months) - 11)):
        window = months[index:index + 12]
        if not window:
            continue
        count = sum(window[0] <= month <= window[-1] for month in eligible_months)
        if count >= peak_count:
            peak_count = count
            peak_from, peak_to = window[0], window[-1]

    ratio = peak_count / households if households > 0 else None
    return {
        "total_pure_jeonse_36m": len(pure_jeonse),
        "eligible_contract_count": len(eligible),
        "renewal_count": len(renewals),
        "peak_12m_count": peak_count,
        "peak_period_from": peak_from,
        "peak_period_to": peak_to,
        "households": households,
        "peak_ratio": ratio,
        "threshold_count": 3,
        "threshold_ratio": 0.3,
    }


def _run_duplicate_contract_check(
    listing_name: str,
    recent_transactions: list[dict],
    data_available: bool | None = None,
) -> ListingCheckResult:
    jeonse_only = [
        t for t in recent_transactions
        if _to_int(t.get("monthlyRent")) == 0
    ]
    count = len(jeonse_only)
    threshold = 5

    if data_available is False or (count == 0 and data_available is not True):
        return ListingCheckResult(
            code="duplicate_contract",
            title="전세 거래 집중도",
            status="unknown",
            reason="최근 전세 거래 데이터를 정상적으로 조회하지 못해 거래 집중도를 판단할 수 없습니다.",
            evidence={"transaction_count": count},
        )

    status = "warn" if count >= threshold else "pass"
    reason = (
        f"최근 동일 건물에서 전세 거래가 {count}건 집중됐습니다. 중복 계약 가능성을 확인하세요."
        if status == "warn"
        else f"최근 동일 건물 전세 거래 {count}건으로 이상 징후가 없습니다."
    )
    return ListingCheckResult(
        code="duplicate_contract",
        title="전세 거래 집중도",
        status=status,
        reason=reason,
        evidence={"transaction_count": count, "threshold": threshold},
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
    """'202511' ~ '202601' 사이의 YYYYMM 목록 반환."""
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
    diagnostics: dict[str, Any] | None = None,
    rh_dong: str = "",
    rh_jibun: str = "",
    debug_dong: str = "",
) -> list[dict]:
    if diagnostics is not None:
        diagnostics["request_count"] = diagnostics.get("request_count", 0) + 1
    url = (
        f"https://apis.data.go.kr/1613000/{svc_name}/{method_name}"
        f"?serviceKey={settings.data_go_kr_api_key}"
        f"&LAWD_CD={lawd_cd}&DEAL_YMD={ymd}&numOfRows=1000&pageNo=1"
    )
    try:
        response = await client.get(url, timeout=10.0)
    except httpx.RequestError as exc:
        if diagnostics is not None:
            diagnostics["request_error_count"] = diagnostics.get("request_error_count", 0) + 1
            if "errors" in diagnostics:
                diagnostics["errors"].append({
                    "service": svc_name,
                    "month": ymd,
                    "kind": "request_error",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                })
        return []
    if response.status_code != 200:
        if diagnostics is not None:
            diagnostics["http_error_count"] = diagnostics.get("http_error_count", 0) + 1
            if "errors" in diagnostics:
                diagnostics["errors"].append({
                    "service": svc_name,
                    "month": ymd,
                    "kind": "http_error",
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type"),
                    "body": response.text[:500],
                })
        return []
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        if diagnostics is not None:
            diagnostics["non_xml_response_count"] = diagnostics.get("non_xml_response_count", 0) + 1
            if "errors" in diagnostics:
                diagnostics["errors"].append({
                    "service": svc_name,
                    "month": ymd,
                    "kind": "non_xml_response",
                    "content_type": response.headers.get("content-type"),
                    "body": response.text[:500],
                })
        return []
    
    if root.findtext(".//resultCode") != "000":
        if diagnostics is not None and "errors" in diagnostics:
            diagnostics["errors"].append({
                "service": svc_name,
                "month": ymd,
                "kind": "api_error",
                "result_code": root.findtext(".//resultCode"),
                "result_message": root.findtext(".//resultMsg"),
            })
        return []
    if diagnostics is not None:
        diagnostics["success_count"] = diagnostics.get("success_count", 0) + 1
    items = root.findall(".//item")
    if diagnostics is not None:
        diagnostics["api_item_count"] = diagnostics.get("api_item_count", 0) + len(items)
    result = []
    for item in items:
        if dong and dong not in (item.findtext("umdNm") or ""):
            continue
        if diagnostics is not None and "raw_transactions" in diagnostics and (item.findtext("umdNm") or "").strip() == debug_dong:
            diagnostics["raw_transactions"].append({
                "service": svc_name,
                "month": ymd,
                "item": {child.tag: child.text or "" for child in item},
            })
        if rh_jibun and not _is_matching_rh_address(rh_dong, rh_jibun, item.findtext("umdNm"), item.findtext("jibun")):
            continue
        current_building_name = item.findtext(building_field) or ""
        if not rh_jibun and building_name and not _is_matching_building(building_name, current_building_name):
            continue

        if diagnostics is not None:
            diagnostics["building_match_count"] = diagnostics.get("building_match_count", 0) + 1

        result.append({
            "buildingNm": current_building_name,
            "umdNm": item.findtext("umdNm"),
            "jibun": item.findtext("jibun"),
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
    recent_transactions = (payload.extra_signals or {}).get("recent_transactions") or []
    checks = [
        _run_deposit_to_market_check(payload.deposit_krw, market_price_krw, "unknown"),  # 등기 유형 미수집
        _run_residential_use_check(payload.selected_building),
        _run_duplicate_contract_check(payload.listing_name, recent_transactions),
    ]
    summary = _summarize_check_overall(checks)
    explanation = await _generate_listing_check_explanation(payload, checks, summary)
    return ListingCheckAnalyzeResponse(
        checks=checks,
        summary=summary,
        llm_explanation=explanation,
        risk_score=_compute_risk_score(checks),
    )


_GRADE_TO_RISK_LEVEL = {"safe": "low", "caution": "medium", "risk": "high", "high_risk": "high"}
_CHECK_STATUS_TO_RISK_LEVEL = {"fail": "high", "warn": "medium", "pass": "low", "unknown": "medium"}


def _chat_analysis_context(row: Analysis) -> AnalysisDetailResponse:
    """저장된 분석을 챗봇이 기대하는 형태로 옮긴다."""
    return AnalysisDetailResponse(
        analysis_id=row.id,
        status="completed",
        overall_risk=_GRADE_TO_RISK_LEVEL[row.risk_grade],
        risk_factors=[
            RiskFactor(
                code=check["code"],
                title=check["title"],
                level=_CHECK_STATUS_TO_RISK_LEVEL[check["status"]],
                detail=check["reason"],
            )
            for check in row.result.get("checks", [])
        ],
        explanation=row.result.get("llm_explanation", ""),
        references=[],
    )


@app.post("/qa")
async def answer_question(payload: QaRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    row = db.get(Analysis, payload.analysis_id) if payload.analysis_id else None
    analysis = _chat_analysis_context(row) if row else None
    if not settings.openai_api_key or not settings.openai_api_key.strip():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CHATBOT_NOT_CONFIGURED",
                "message": "OPENAI_API_KEY is not configured.",
                "action_hint": "OPENAI_API_KEY를 설정한 뒤 서버를 다시 시작하세요.",
            },
        )

    async def event_stream():
        try:
            async for event, data in chatbot_service.stream_answer_question(
                question=payload.question,
                history=payload.history,
                analysis=analysis,
            ):
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception:
            logger.exception("Chatbot stream failed")
            error = {
                "code": "CHATBOT_UPSTREAM_ERROR",
                "message": "챗봇 응답 생성 중 외부 모델 호출에 실패했습니다.",
                "action_hint": "잠시 후 다시 시도하세요.",
            }
            yield f"event: error\ndata: {json.dumps(error, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# R1~R8 마법사 (`/risk/assess`) — docs/전세사기위험도판별핵심로직.md 구현
# ---------------------------------------------------------------------------


def _allocate_shared_collateral(mortgage_items: list[MortgageItem]) -> int:
    """공동담보 채권최고액을 물건 수로 나눠 이 호실 몫만 남긴다 (민법 368① 비례배분).

    원칙은 각 부동산의 경매대가에 비례한 배분이지만 다른 호실의 시세를 알 수 없으므로
    물건 수 균등 배분으로 근사한다. 배분하지 않으면 건물 전체 채권최고액이 호실 한 채
    시세로 나뉘어 전세가율이 수백~수천 %로 튄다.
    """
    return sum(round(item.amount_krw / item.shared_property_count) for item in mortgage_items)


def _run_mortgage_ratio_check(
    mortgage_items: list[MortgageItem],
    deposit_krw: int,
    market_price_krw: int,
    registry_type: str,
) -> ListingCheckResult:
    """R2. 채권최고액 / 시세. 일반건물은 분모(시세)가 없어 구조적으로 판정 불가."""
    title = "근저당 비율"
    mortgage_total_krw = sum(item.amount_krw for item in mortgage_items)
    allocated_krw = _allocate_shared_collateral(mortgage_items)
    is_shared = any(item.shared_property_count > 1 for item in mortgage_items)
    base_evidence = {
        "mortgage_total_krw": mortgage_total_krw,
        "allocated_mortgage_krw": allocated_krw,
        "shared_collateral": [item.model_dump() for item in mortgage_items],
        "market_price_krw": market_price_krw,
        "registry_type": registry_type,
    }

    if registry_type == "unknown":
        return ListingCheckResult(
            code="mortgage_ratio",
            title=title,
            status="unknown",
            reason="등기부등본이 제출되지 않아 채권최고액을 확인할 수 없습니다.",
            evidence=base_evidence,
        )
    if registry_type == "general_building":
        return ListingCheckResult(
            code="mortgage_ratio",
            title=title,
            status="unknown",
            reason="일반건물(단독·다가구)은 건물 전체가 하나의 등기라 호실 시세가 산출되지 않습니다. 분모를 확보할 수 없어 판정하지 않습니다.",
            evidence=base_evidence,
        )
    if market_price_krw <= 0:
        return ListingCheckResult(
            code="mortgage_ratio",
            title=title,
            status="unknown",
            reason="시세를 확보하지 못해 근저당 비율을 계산할 수 없습니다.",
            evidence=base_evidence,
        )

    ratio = allocated_krw / market_price_krw
    combined_ratio = (allocated_krw + deposit_krw) / market_price_krw
    evidence = {
        **base_evidence,
        "deposit_krw": deposit_krw,
        "ratio": round(ratio, 4),
        "combined_ratio": round(combined_ratio, 4),
        "worst_case_combined_ratio": round((mortgage_total_krw + deposit_krw) / market_price_krw, 4),
        "threshold_fail": 0.6,
        "threshold_warn": 0.4,
        "threshold_combined": 0.8,
    }
    # 비례배분은 동시배당을 전제한다. 은행이 이 호실만 먼저 경매에 넣는 이시배당에서는
    # 원문 전액이 걸릴 수 있으므로, 배분을 적용했다는 사실과 원문 금액을 함께 알린다.
    shared_note = (
        f" 공동담보 {max(item.shared_property_count for item in mortgage_items)}건에 비례배분한 금액 기준입니다."
        f" 원문 채권최고액 합계는 {mortgage_total_krw:,}원이며, 이 호실만 먼저 경매에 넘어가는"
        " 이시배당에서는 전액이 부담될 수 있습니다."
        if is_shared
        else ""
    )

    # R2-b: 근저당 단독으로는 안전해도 보증금과 합쳐 80%를 넘으면 fail (§1 핵심 부등식)
    if combined_ratio > 0.8:
        return ListingCheckResult(
            code="mortgage_ratio",
            title=title,
            status="fail",
            reason=f"채권최고액과 보증금의 합이 시세의 {combined_ratio:.0%}로 80%를 초과합니다. 경매 시 보증금 회수가 어렵습니다.{shared_note}",
            evidence=evidence,
        )
    if ratio > 0.6:
        return ListingCheckResult(
            code="mortgage_ratio",
            title=title,
            status="fail",
            reason=f"채권최고액이 시세의 {ratio:.0%}로 60%를 초과합니다.{shared_note}",
            evidence=evidence,
        )
    if ratio > 0.4:
        return ListingCheckResult(
            code="mortgage_ratio",
            title=title,
            status="warn",
            reason=f"채권최고액이 시세의 {ratio:.0%}입니다. 40~60% 구간으로 주의가 필요합니다.{shared_note}",
            evidence=evidence,
        )
    return ListingCheckResult(
        code="mortgage_ratio",
        title=title,
        status="pass",
        reason=f"채권최고액이 시세의 {ratio:.0%}로 안전 구간입니다.{shared_note}",
        evidence=evidence,
    )


def _split_owner_names(value: str) -> list[str]:
    return [name for name in re.split(r"[,/·\s]+", value.strip()) if name]


def _run_owner_mismatch_check(contract_owner_name: str, registry_owner_name: str) -> ListingCheckResult:
    """R3. 계약서상 임대인이 등기부 갑구 소유자와 일치하는지. 공동소유면 전원이 계약 당사자여야 한다."""
    title = "계약서 임대인과 등기부 소유자 일치"
    registry_owners = _split_owner_names(registry_owner_name)
    contract_owners = _split_owner_names(contract_owner_name)
    evidence = {
        "registry_owners": registry_owners,
        "contract_owners": contract_owners,
    }

    if not registry_owners or not contract_owners:
        return ListingCheckResult(
            code="owner_mismatch",
            title=title,
            status="unknown",
            reason="등기부 소유자명 또는 계약서상 임대인명이 없어 대조할 수 없습니다.",
            evidence=evidence,
        )

    missing = [owner for owner in registry_owners if owner not in contract_owners]
    if missing:
        return ListingCheckResult(
            code="owner_mismatch",
            title=title,
            status="fail",
            reason=f"등기부상 소유자 {', '.join(missing)}이(가) 계약 당사자에 포함되어 있지 않습니다.",
            evidence={**evidence, "missing_owners": missing},
        )
    return ListingCheckResult(
        code="owner_mismatch",
        title=title,
        status="pass",
        reason="등기부상 소유자가 모두 계약 당사자에 포함되어 있습니다. 다만 신분증·위임장 확인은 별도로 필요합니다.",
        evidence=evidence,
    )


def _run_rights_encumbrance_check(
    critical_terms: list[dict[str, Any]],
    registry_type: str,
) -> ListingCheckResult:
    """R4. 압류·가압류·가처분·가등기·경매개시결정·신탁. 하나라도 유효하면 고위험 오버라이드."""
    title = "권리침해 등기 존재 여부"

    if registry_type == "unknown":
        return ListingCheckResult(
            code="rights_encumbrance",
            title=title,
            status="unknown",
            reason="등기부등본이 제출되지 않아 권리침해 등기를 확인할 수 없습니다.",
            evidence={"critical_terms": critical_terms},
        )

    # is_cancelled가 null이면 말소 여부 불확실 → 보수적으로 유효로 간주한다.
    active = [term for term in critical_terms if term.get("is_cancelled") is not True]
    if not active:
        return ListingCheckResult(
            code="rights_encumbrance",
            title=title,
            status="pass",
            reason="말소되지 않은 압류·가압류·가처분·가등기·경매·신탁 등기가 없습니다.",
            evidence={"critical_terms": critical_terms},
        )

    terms = ", ".join(str(term.get("term") or "권리침해") for term in active)
    has_trust = any("신탁" in str(term.get("term") or "") for term in active)
    reason = f"말소되지 않은 {terms} 등기가 있습니다."
    if has_trust:
        reason += " 신탁등기가 있으면 처분 권한이 수탁자에게 있어, 등기부상 소유자와 계약해도 무효가 될 수 있습니다. 신탁회사 동의서를 반드시 확인하세요."
    return ListingCheckResult(
        code="rights_encumbrance",
        title=title,
        status="fail",
        reason=reason,
        evidence={"critical_terms": critical_terms, "active_terms": active, "has_trust": has_trust},
    )


def _run_illegal_building_check(status: str) -> ListingCheckResult:
    """R6. 위반건축물 표시. 보증보험 가입 거절 사유.

    건축물대장 공공 API에는 위반건축물 필드가 없어 대장 원본을 봐야만 알 수 있다.
    확인하지 못한 상태를 pass로 두면 미탐이 통과로 위장되므로 unknown으로 남긴다.
    """
    title = "위반건축물 여부"
    if status == "present":
        return ListingCheckResult(
            code="illegal_building",
            title=title,
            status="fail",
            reason="건축물대장에 위반건축물로 표시되어 있습니다. 전세보증보험 가입이 거절되고 이행강제금 대상이 될 수 있습니다.",
            evidence={"illegal_building_status": status},
        )
    if status == "absent":
        return ListingCheckResult(
            code="illegal_building",
            title=title,
            status="pass",
            reason="건축물대장에 위반건축물 표시가 없습니다.",
            evidence={"illegal_building_status": status},
        )
    return ListingCheckResult(
        code="illegal_building",
        title=title,
        status="unknown",
        reason="건축물대장을 확인하지 못해 위반건축물 여부를 판정할 수 없습니다. 정부24에서 건축물대장을 발급해 업로드하세요.",
        evidence={"illegal_building_status": status},
    )


def _run_jeonse_concentration_check(
    total_count: int,
    peak_12m_count: int,
    households: int,
    data_status: str,
    registry_type: str,
) -> ListingCheckResult:
    """R7. 최근 3년 중 가장 집중된 12개월의 신규 전세를 세대수 대비로 본다."""
    ratio = peak_12m_count / households if households > 0 else None
    evidence = {
        "total_pure_jeonse_36m": total_count,
        "peak_12m_count": peak_12m_count,
        "households": households,
        "peak_ratio": ratio,
        "threshold_count": 3,
        "threshold_ratio": 0.3,
    }
    if registry_type != "general_building":
        return ListingCheckResult(
            code="duplicate_contract",
            title="전세 거래 집중도",
            status="unknown",
            reason="집합건물은 호실별 소유자가 다를 수 있어 건물 전체 거래량을 위험 점수에 반영하지 않고 참고 정보로만 제공합니다.",
            evidence=evidence,
        )
    if data_status not in ("complete", "manual") or ratio is None:
        return ListingCheckResult(
            code="duplicate_contract",
            title="전세 거래 집중도",
            status="unknown",
            reason="전세 거래 데이터 또는 총 세대수가 부족해 거래 집중도를 판단할 수 없습니다.",
            evidence=evidence,
        )

    status = "warn" if peak_12m_count >= 3 and ratio >= 0.3 else "pass"
    reason = (
        f"최근 3년 중 가장 집중된 12개월에 {peak_12m_count}건이 신고되어 전체 {households}세대의 {ratio:.0%}입니다. 추가 확인이 필요합니다."
        if status == "warn"
        else f"최근 3년 중 가장 집중된 12개월의 전세 거래가 {peak_12m_count}건으로 전체 {households}세대의 {ratio:.0%}입니다. 거래 집중 신호가 없습니다."
    )
    return ListingCheckResult(
        code="duplicate_contract",
        title="전세 거래 집중도",
        status=status,
        reason=reason,
        evidence=evidence,
    )


def _run_senior_deposit_check(
    senior_deposit_krw: int | None,
    mortgage_total_krw: int,
    deposit_krw: int,
    market_price_krw: int,
    registry_type: str,
) -> ListingCheckResult:
    """R8. 일반건물(단독·다가구) 전용. 선순위 보증금까지 합산한 §1 핵심 부등식."""
    title = "선순위 보증금 합산 부담률"
    evidence = {
        "senior_deposit_krw": senior_deposit_krw,
        "mortgage_total_krw": mortgage_total_krw,
        "deposit_krw": deposit_krw,
        "market_price_krw": market_price_krw,
        "registry_type": registry_type,
    }

    if registry_type == "unknown":
        return ListingCheckResult(
            code="senior_deposit",
            title=title,
            status="unknown",
            reason="등기부등본이 제출되지 않아 등기 유형을 알 수 없습니다. 일반건물이면 선순위 보증금 확인이 필수입니다.",
            evidence=evidence,
        )
    if registry_type != "general_building":
        return ListingCheckResult(
            code="senior_deposit",
            title=title,
            status="pass",
            reason="집합건물은 호실별로 등기가 분리되어 선순위 보증금 문제가 발생하지 않습니다.",
            evidence=evidence,
        )
    if senior_deposit_krw is None:
        return ListingCheckResult(
            code="senior_deposit",
            title=title,
            status="unknown",
            reason="선순위 보증금 합계를 확인하지 못해 부담률을 계산할 수 없습니다.",
            evidence=evidence,
        )
    if market_price_krw <= 0:
        return ListingCheckResult(
            code="senior_deposit",
            title=title,
            status="unknown",
            reason="시세를 확보하지 못해 선순위 보증금 부담률을 계산할 수 없습니다.",
            evidence=evidence,
        )

    total = senior_deposit_krw + mortgage_total_krw + deposit_krw
    ratio = total / market_price_krw
    evidence = {**evidence, "total_burden_krw": total, "ratio": round(ratio, 4), "threshold": 0.8}
    if ratio > 0.8:
        return ListingCheckResult(
            code="senior_deposit",
            title=title,
            status="fail",
            reason=f"선순위 보증금·채권최고액·내 보증금의 합이 시세의 {ratio:.0%}로 80%를 초과합니다.",
            evidence=evidence,
        )
    return ListingCheckResult(
        code="senior_deposit",
        title=title,
        status="pass",
        reason=f"선순위 보증금까지 합산한 부담률이 시세의 {ratio:.0%}로 안전 구간입니다.",
        evidence=evidence,
    )


def _risk_grade(score: int) -> str:
    if score >= 60:
        return "high_risk"
    if score >= 30:
        return "risk"
    if score >= 15:
        return "caution"
    return "safe"


def _collect_override_reasons(
    checks: list[ListingCheckResult],
    payload: RiskAssessRequest,
) -> list[str]:
    """§4-5 고위험 오버라이드. 치명적 단일 결함이 가중 합산으로 희석되는 것을 막는다."""
    by_code = {check.code: check for check in checks}
    reasons: list[str] = []

    if by_code["rights_encumbrance"].status == "fail":
        reasons.append("말소되지 않은 압류·가압류·경매개시결정·신탁 등기가 존재합니다. (R4)")
    if by_code["owner_mismatch"].status == "fail":
        reasons.append("계약서상 임대인이 등기부상 소유자와 일치하지 않습니다. (R3)")

    market_price = payload.market_price_krw
    if market_price > 0:
        # 공동담보 배분 후 금액으로 판단한다. 원문 합계를 쓰면 건물 전체 부채가
        # 호실 한 채 시세로 나뉘어 시세 초과 오버라이드가 상시 발동한다.
        mortgage_krw = by_code["mortgage_ratio"].evidence.get(
            "allocated_mortgage_krw", payload.mortgage_total_krw
        )
        combined = (mortgage_krw + payload.deposit_krw) / market_price
        # 낙찰가율 70~80%를 감안하면 90%도 사실상 전액 손실. 100%는 너무 느슨하다.
        if combined > _COMBINED_OVERRIDE_THRESHOLD:
            reasons.append(
                f"채권최고액과 보증금의 합이 시세의 {combined:.0%}로 경매 회수 가능 범위를 넘습니다. (R2-b)"
            )
    return reasons


async def _generate_risk_assessment_explanation(
    payload: RiskAssessRequest,
    checks: list[ListingCheckResult],
    summary: ListingCheckSummary,
    risk_score: int,
    risk_grade: str,
    override_reasons: list[str],
) -> str:
    if not settings.openai_api_key or not settings.openai_api_key.strip():
        return "규칙 기반 점검 결과입니다. OPENAI_API_KEY가 없어 자연어 설명은 생략됩니다."

    model = ChatOpenAI(
        model=_RISK_ASSESSMENT_MODEL,
        api_key=settings.openai_api_key,
        reasoning_effort=_RISK_ASSESSMENT_REASONING_EFFORT,
        temperature=0.1,
    )
    context_data = {
        "매물": payload.listing_name,
        "보증금": payload.deposit_krw,
        "시세": payload.market_price_krw,
        "등기 유형": payload.registry_type,
        "규칙 점검 결과": [check.model_dump() for check in checks],
        "종합 상태": summary.model_dump(),
        "위험 점수": risk_score,
        "위험 등급": risk_grade,
        "고위험 오버라이드 사유": override_reasons,
    }
    messages = [
        SystemMessage(content=_RISK_ASSESSMENT_SYSTEM_PROMPT),
        HumanMessage(
            content="다음 점검 결과를 임차인이 이해할 수 있게 설명해줘. "
            "판정은 이미 규칙이 내렸으니 숫자나 등급을 바꾸지 말고 설명만 해줘:\n\n"
            + json.dumps(context_data, ensure_ascii=False, indent=2)
        ),
    ]
    try:
        result = await asyncio.to_thread(model.invoke, messages)
        content = result.content if isinstance(result.content, str) else str(result.content)
        return content.strip() or "점검 결과를 분석했지만 설명 문장을 생성하지 못했습니다."
    except Exception as exc:
        logger.warning("risk assessment explanation failed: %s", exc)
        return "규칙 결과를 기반으로 점검을 완료했습니다. 모델 설명 생성 중 오류가 발생했습니다."


@app.post("/risk/assess", response_model=RiskAssessResponse)
async def assess_risk(
    payload: RiskAssessRequest,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> RiskAssessResponse:
    if payload.deposit_krw <= 0:
        raise HTTPException(status_code=400, detail="deposit_krw는 0보다 커야 합니다.")

    checks = [
        _run_deposit_to_market_check(
            payload.deposit_krw, payload.market_price_krw, payload.registry_type
        ),
        _run_mortgage_ratio_check(
            payload.mortgage_items,
            payload.deposit_krw,
            payload.market_price_krw,
            payload.registry_type,
        ),
        _run_owner_mismatch_check(payload.contract_owner_name, payload.registry_owner_name),
        _run_rights_encumbrance_check(payload.critical_terms, payload.registry_type),
        _run_residential_use_check(
            {"building_type": payload.building_type, "detail_use": payload.detail_use}
        ),
        _run_illegal_building_check(payload.illegal_building_status),
        _run_jeonse_concentration_check(
            payload.recent_jeonse_count,
            payload.recent_jeonse_peak_12m_count,
            payload.households,
            payload.recent_jeonse_data_status,
            payload.registry_type,
        ),
        _run_senior_deposit_check(
            payload.senior_deposit_krw,
            payload.mortgage_total_krw,
            payload.deposit_krw,
            payload.market_price_krw,
            payload.registry_type,
        ),
    ]
    summary = _summarize_check_overall(checks)
    risk_score = _compute_risk_score(checks)
    score_grade = _risk_grade(risk_score)
    override_reasons = _collect_override_reasons(checks, payload)
    risk_grade = "high_risk" if override_reasons else score_grade
    explanation = await _generate_risk_assessment_explanation(
        payload, checks, summary, risk_score, risk_grade, override_reasons
    )
    response = RiskAssessResponse(
        checks=checks,
        summary=summary,
        risk_score=risk_score,
        score_max=_RISK_SCORE_MAX,
        score_grade=score_grade,
        score_ranges=list(_RISK_SCORE_RANGES),
        score_breakdown=_build_score_breakdown(checks),
        risk_grade=risk_grade,
        override_reasons=override_reasons,
        llm_explanation=explanation,
        analysis_id=str(uuid4()),
    )
    db.add(
        Analysis(
            id=response.analysis_id,
            user_id=user.id if user else None,
            listing_name=payload.listing_name[:200],
            deposit_krw=payload.deposit_krw,
            market_price_krw=payload.market_price_krw,
            risk_grade=risk_grade,
            risk_score=risk_score,
            request=payload.model_dump(mode="json"),
            result=response.model_dump(mode="json"),
        )
    )
    db.commit()
    return response
