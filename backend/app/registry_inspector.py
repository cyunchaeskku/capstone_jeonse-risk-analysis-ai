import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .settings import settings


REGISTRY_INSPECTION_SYSTEM_PROMPT = """
너는 한국 부동산 등기사항증명서 검토 보조 시스템이다.

핵심 원칙:
- 입력된 등기사항증명서 텍스트에서 전세계약 위험 검토에 필요한 특이사항을 추출한다.
- 법률 자문이나 최종 계약 판단을 하지 않는다.
- 텍스트에 명시된 내용만 근거로 사용한다.
- 위험도 공식 계산은 하지 않는다.
- deterministic parser가 계산해야 할 값을 임의로 만들지 않는다.
- 수치가 원문에 있으면 반드시 금액/면적/층수 등 구체적 숫자를 explanation 또는 evidence에 포함한다.
- 좋은 신호도 findings에 포함한다. 위험 요소만 출력하지 않는다.
- 좋은 신호는 severity를 "info"로 두고, 왜 좋은 신호인지 짧게 설명한다.
- 말소사항 포함 문서에서는 말소된 권리와 현재 유효해 보이는 권리를 구분한다.
- 텍스트만으로 말소 여부가 불확실하면 is_cancelled를 null로 둔다.
- 개인정보는 필요한 최소 범위만 사용하고 주민등록번호 뒷자리는 절대 출력하지 않는다.
- 출력은 반드시 JSON만 반환한다.

검토 범위:

1. 표제부 검토
- 부동산 종류를 판별한다.
- 첫 페이지 또는 표제부에 "집합건물"이 있으면 집합건물로 분류한다.
- "건물", "토지"가 별도 등기처럼 보이거나 단독/다가구 구조로 보이면 일반건물 후보로 분류한다.
- 일반건물 또는 다가구/단독건물 후보이면 다음 안내를 findings에 포함한다:
  "나보다 먼저 들어온 다른 세입자들의 총 보증금(선순위 보증금)을 추가로 확인해야 합니다."
- 주요 용도를 추출한다.
- 위험 용도 단어를 탐지한다:
  "고시원", "다중생활시설", "근린생활시설", "상가", "업무용 오피스텔", "오피스텔(업무용)"
- 위험 용도 단어가 있으면 전세보증보험 가입 제한, 전입신고 또는 주거 적합성 문제가 생길 수 있음을 경고한다.
- "근린생활시설"이 주거처럼 사용되는 경우 근생빌라 가능성을 경고한다.
- 주거용도가 명확히 확인되면 좋은 신호로 findings에 포함한다.
- 주거용도가 아닌 용도(예: 고시원, 사무소, 근린생활시설, 업무시설)가 확인되면 해당 용도명을 반드시 포함해 경고한다.

2. 갑구 검토
- 현재 최종 소유자를 추출한다.
- 순위번호상 마지막에 있고 말소되지 않은 소유권 관련 항목을 우선한다.
- 소유자 이름, 주민등록번호 앞자리, 주소를 추출하되 주민등록번호 뒷자리는 마스킹한다.
- 현재 소유자 정보가 있으면 다음 안내를 findings에 포함한다:
  "계약서상의 임대인과 등기부상 소유자가 일치하는지 신분증으로 대조해야 합니다."
- 갑구 위험 단어를 탐지한다:
  "압류", "가압류", "가처분", "가등기", "경매개시결정", "신탁"
- 위 단어가 말소되지 않고 현재 유효해 보이면 severity를 "critical"로 둔다.
- 이 경우 강한 위험 경고를 출력한다:
  "소유권 제한 또는 재정 위험 신호가 있어 계약 전 반드시 등기소, 변호사, 공인중개사 등 전문가 확인이 필요합니다."
- "신탁"이 유효해 보이면 다음 안내를 포함한다:
  "신탁 등기가 있으면 실제 처분 권한이 신탁회사에 있을 수 있으므로 신탁회사 동의서 또는 계약 권한 확인이 필요합니다."

3. 을구 검토
- 근저당권, 전세권, 임차권등기, 지상권 등 소유권 외 권리를 탐지한다.
- 채권최고액은 발견된 원문과 금액을 함께 기록한다.
- 변경 등기로 채권최고액이 바뀐 경우 변경 후 금액 후보를 함께 표시한다.
- 근저당권이나 채권최고액을 설명할 때는 "현재 채권최고액 3,360,000,000원"처럼 숫자를 반드시 포함한다.
- 채권최고액이 크다/작다 같은 평가는 현재 건물 시세가 없으면 단정하지 않는다. 대신 "시세 입력 후 위험도 계산 필요"라고 안내한다.
- 말소된 근저당권과 유효해 보이는 근저당권을 구분한다.
- 을구에 권리 기록이 없거나 근저당권이 확인되지 않으면 좋은 신호로 findings에 포함한다.

좋은 신호 예시:
- "현재 건물 용도가 공동주택/아파트/다세대주택 등 주거용으로 확인됩니다. 이는 전입신고와 보증보험 검토 측면에서 좋은 신호입니다."
- "갑구에서 압류, 가압류, 가처분, 경매개시결정, 신탁 같은 소유권 제한 단어가 확인되지 않습니다. 이는 좋은 신호입니다."
- "을구에서 근저당권이 확인되지 않습니다. 선순위 담보권 부담이 낮을 가능성이 있어 좋은 신호입니다."

나쁜 신호 예시:
- "현재 채권최고액 3,360,000,000원이 확인됩니다. 시세, 내 보증금, 선순위보증금을 함께 입력해 위험도 계산이 필요합니다."
- "건물 용도에 고시원, 사무소가 확인됩니다. 일반 주거용 계약과 다를 수 있어 전입신고, 보증보험 가능 여부를 확인해야 합니다."

출력 JSON schema:
{
  "property_section": {
    "registry_type": "aggregate_building|general_building|land|unknown",
    "main_use": "string|null",
    "risk_use_terms": ["string"],
    "notes": ["string"]
  },
  "ownership_section": {
    "current_owner": {
      "name": "string|null",
      "birth_prefix": "string|null",
      "address": "string|null"
    },
    "owner_verification_message": "string|null",
    "critical_terms": [
      {
        "term": "압류|가압류|가처분|가등기|경매개시결정|신탁",
        "is_cancelled": true,
        "evidence": "string",
        "warning": "string"
      }
    ]
  },
  "rights_section": {
    "mortgages": [
      {
        "amount_krw": 0,
        "raw_text": "string",
        "is_cancelled": false,
        "evidence": "string"
      }
    ],
    "other_rights": [
      {
        "type": "string",
        "evidence": "string",
        "is_cancelled": false
      }
    ]
  },
  "findings": [
    {
      "category": "title|ownership|mortgage|seizure|auction|trust|use|senior_deposit|other",
      "severity": "info|caution|risk|critical",
      "title": "string",
      "evidence": "string",
      "explanation": "string",
      "recommended_action": "string"
    }
  ],
  "needs_human_review": true
}
""".strip()


REGISTRY_INSPECTION_USER_PROMPT_TEMPLATE = """
다음은 부동산 등기사항증명서 PDF에서 추출한 텍스트다.

위 system 규칙에 따라 전세계약 전 위험 검토용 특이사항을 JSON으로 추출하라.
말소 여부가 불확실하면 is_cancelled를 false로 단정하지 말고 null로 표시하라.
원문에 없는 정보는 null 또는 빈 배열로 둬라.
deterministic parser가 추출한 채권최고액 후보도 함께 참고하라. 이 금액을 언급할 때는 반드시 숫자를 포함하라.

채권최고액 후보:
{max_claim_context}

등기 텍스트:
---
{registry_text}
---
""".strip()


def inspect_registry_text(registry_text: str, max_claim_amounts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if not settings.openai_api_key or not settings.openai_api_key.strip():
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    if not registry_text.strip():
        return _fallback_result("등기사항증명서 텍스트가 비어 있습니다.")

    model = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    response = model.invoke(
        [
            SystemMessage(content=REGISTRY_INSPECTION_SYSTEM_PROMPT),
            HumanMessage(
                content=REGISTRY_INSPECTION_USER_PROMPT_TEMPLATE.format(
                    registry_text=registry_text,
                    max_claim_context=_format_max_claim_context(max_claim_amounts or []),
                )
            ),
        ]
    )
    content = response.content if isinstance(response.content, str) else json.dumps(response.content, ensure_ascii=False)
    return _coerce_inspection_payload(content)


def _coerce_inspection_payload(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fence(content))
    except json.JSONDecodeError:
        return _fallback_result("LLM 응답을 JSON으로 해석하지 못했습니다.", raw_response=content)

    if not isinstance(payload, dict):
        return _fallback_result("LLM 응답 최상위 값이 객체가 아닙니다.", raw_response=content)

    payload.setdefault("property_section", {"registry_type": "unknown", "main_use": None, "risk_use_terms": [], "notes": []})
    payload.setdefault(
        "ownership_section",
        {
            "current_owner": {"name": None, "birth_prefix": None, "address": None},
            "owner_verification_message": None,
            "critical_terms": [],
        },
    )
    payload.setdefault("rights_section", {"mortgages": [], "other_rights": []})
    payload.setdefault("findings", [])
    payload.setdefault("needs_human_review", True)
    return payload


def _format_max_claim_context(max_claim_amounts: list[dict[str, Any]]) -> str:
    if not max_claim_amounts:
        return "- 없음"
    lines = []
    for item in max_claim_amounts:
        amount = item.get("amount_krw")
        raw_text = item.get("raw_text") or ""
        page = item.get("page")
        amount_text = f"{int(amount):,}원" if isinstance(amount, int) else "금액 확인 필요"
        page_text = f"page {page}" if page else "page unknown"
        lines.append(f"- {amount_text} ({page_text}): {raw_text}")
    lines.append("- 여러 후보가 있으면 마지막 후보를 현재 유효 후보로 보되, 확정이 필요하다고 표현한다.")
    return "\n".join(lines)


def _strip_code_fence(content: str) -> str:
    text = content.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return fence_match.group(1).strip() if fence_match else text


def _fallback_result(message: str, raw_response: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "property_section": {
            "registry_type": "unknown",
            "main_use": None,
            "risk_use_terms": [],
            "notes": [],
        },
        "ownership_section": {
            "current_owner": {
                "name": None,
                "birth_prefix": None,
                "address": None,
            },
            "owner_verification_message": None,
            "critical_terms": [],
        },
        "rights_section": {
            "mortgages": [],
            "other_rights": [],
        },
        "findings": [
            {
                "category": "other",
                "severity": "caution",
                "title": "등기 특이사항 자동 추출 확인 필요",
                "evidence": "",
                "explanation": message,
                "recommended_action": "등기부등본 원문을 직접 확인하거나 다시 업로드하세요.",
            }
        ],
        "needs_human_review": True,
    }
    if raw_response:
        result["raw_response"] = raw_response
    return result
