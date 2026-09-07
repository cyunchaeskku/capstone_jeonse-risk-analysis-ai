"""건축물대장 PDF 판독.

건축물대장은 정부24에서 이미지 스캔본으로 발급된다. 텍스트 레이어가 없어
등기부(registry_parser)처럼 정규식으로 뽑을 수 없으므로 비전 모델로 읽는다.

이 경로가 필요한 이유는 위반건축물 표시 하나 때문이다. 나머지 항목(주용도,
층별 현황, 세대수)은 공공 API(BldRgstHubService)로 다 나오지만, 위반건축물은
API 스키마에 아예 없어서 문서를 직접 보는 수밖에 없다.
"""

import base64
import json
import re
from typing import Any

import fitz
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .settings import settings


# 대장은 보통 1~2쪽이다. 여러 동을 한꺼번에 받은 경우를 감안해 여유를 둔다.
_MAX_PAGES = 6
_RENDER_DPI = 170

BUILDING_REGISTER_SYSTEM_PROMPT = """
너는 한국 건축물대장 판독 보조 시스템이다.

핵심 원칙:
- 이미지에 실제로 보이는 내용만 사용한다. 추측하거나 일반 상식으로 채우지 않는다.
- 보이지 않거나 확신할 수 없으면 null 또는 "unclear"로 둔다. 임의로 정상값을 넣지 않는다.
- 위험도 점수나 최종 계약 판단을 하지 않는다. 판정은 규칙 엔진이 한다.
- 개인정보는 출력하지 않는다. 건축주·설계자·시공자 등 사람 이름과
  면허(등록)번호, 주민등록번호는 어떤 필드에도 넣지 않는다.
- 출력은 반드시 JSON만 반환한다. 설명 문장이나 코드펜스를 붙이지 않는다.

가장 중요한 항목: 위반건축물 표시

건축물대장에 위반 사항이 있으면 문서 상단(제목 "건축물대장" 주변이나
명칭 칸 근처)에 "위반건축물"이라는 표시가 별도로 찍힌다. 보통 굵은 글씨나
빨간 글씨, 도장 형태다.

- 그 표시가 보이면 violation_status = "present"
- 문서를 다 확인했고 그런 표시가 없으면 violation_status = "absent"
- 해상도가 낮거나 잘려서 확인이 안 되면 violation_status = "unclear"

주의: "위반건축물" 표시는 없는 것이 정상이다. 없다고 해서 억지로 찾지 말고,
확실히 안 보이면 "absent"로 둔다. 반대로 조금이라도 보이면 "present"다.
또한 '그 밖의 기재사항'이나 '변동사항' 칸에 위반·시정명령·이행강제금 관련
문구가 있으면 violation_note에 원문을 그대로 옮기고 "present"로 둔다.

함께 추출할 항목:
- 명칭, 대지위치(지번주소), 도로명주소
- 주용도, 세대수/가구수/호수
- 사용승인일 (YYYY-MM-DD 또는 원문 그대로)
- 층별 건축물 현황: 층, 용도, 면적(㎡)
- 그 밖의 기재사항, 변동사항 중 특이 문구

출력 JSON 스키마:
{
  "violation_status": "present" | "absent" | "unclear",
  "violation_note": string | null,
  "building_name": string | null,
  "lot_address": string | null,
  "road_address": string | null,
  "main_use": string | null,
  "households": string | null,
  "use_approval_date": string | null,
  "floors": [{"floor": string, "use": string, "area_m2": number | null}],
  "notes": [string],
  "needs_human_review": boolean
}

violation_status가 "unclear"이면 needs_human_review는 반드시 true다.
"""

BUILDING_REGISTER_USER_PROMPT = """
아래는 건축물대장 PDF를 쪽 순서대로 렌더링한 이미지다.
모든 쪽을 확인한 뒤 위 스키마에 맞는 JSON 하나만 반환하라.
특히 위반건축물 표시 여부를 문서 상단에서 반드시 확인하라.
"""


def render_pdf_pages(pdf_bytes: bytes) -> list[str]:
    """PDF를 쪽별 PNG base64로 변환한다."""
    images: list[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in list(doc)[:_MAX_PAGES]:
            pixmap = page.get_pixmap(dpi=_RENDER_DPI)
            images.append(base64.b64encode(pixmap.tobytes("png")).decode("ascii"))
    return images


def inspect_building_register_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    if not settings.openai_api_key or not settings.openai_api_key.strip():
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    images = render_pdf_pages(pdf_bytes)
    if not images:
        return _fallback_result("PDF에서 페이지를 읽지 못했습니다.")

    model = ChatOpenAI(
        model=settings.openai_vision_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": BUILDING_REGISTER_USER_PROMPT}]
    content.extend(
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}}
        for image in images
    )

    response = model.invoke(
        [SystemMessage(content=BUILDING_REGISTER_SYSTEM_PROMPT), HumanMessage(content=content)]
    )
    raw = response.content if isinstance(response.content, str) else json.dumps(response.content, ensure_ascii=False)
    return _coerce_payload(raw, page_count=len(images))


def _coerce_payload(content: str, page_count: int) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fence(content))
    except json.JSONDecodeError:
        return _fallback_result("판독 결과를 JSON으로 해석하지 못했습니다.", raw_response=content)

    if not isinstance(payload, dict):
        return _fallback_result("판독 결과 최상위 값이 객체가 아닙니다.", raw_response=content)

    status = payload.get("violation_status")
    # 모델이 엉뚱한 값을 주면 안전한 쪽(unclear)으로 떨어뜨린다.
    # 확인 못 한 것을 "위반 없음"으로 바꾸면 미탐이 통과로 위장된다.
    if status not in ("present", "absent", "unclear"):
        payload["violation_status"] = "unclear"

    payload.setdefault("violation_note", None)
    payload.setdefault("building_name", None)
    payload.setdefault("lot_address", None)
    payload.setdefault("road_address", None)
    payload.setdefault("main_use", None)
    payload.setdefault("households", None)
    payload.setdefault("use_approval_date", None)
    payload.setdefault("floors", [])
    payload.setdefault("notes", [])
    payload["page_count"] = page_count
    payload["needs_human_review"] = bool(payload.get("needs_human_review")) or payload["violation_status"] == "unclear"
    return payload


def _strip_code_fence(content: str) -> str:
    text = content.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return fence_match.group(1).strip() if fence_match else text


def _fallback_result(message: str, raw_response: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "violation_status": "unclear",
        "violation_note": None,
        "building_name": None,
        "lot_address": None,
        "road_address": None,
        "main_use": None,
        "households": None,
        "use_approval_date": None,
        "floors": [],
        "notes": [message],
        "page_count": 0,
        "needs_human_review": True,
    }
    if raw_response:
        result["raw_response"] = raw_response
    return result
