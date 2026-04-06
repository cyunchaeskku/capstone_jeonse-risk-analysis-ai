from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .schemas import AnalysisDetailResponse, ChatHistoryMessage, QaResponse
from .settings import settings

DISCLAIMER = "이 답변은 참고용 정보이며, 구체적 사실관계에 따라 달라질 수 있으므로 법률 전문가 상담이 필요할 수 있습니다."
SCOPE = "jeonse-legal-assistant"

SYSTEM_PROMPT = """
당신은 한국 전세 계약 위험 확인과 법률/절차 설명을 돕는 도메인 특화 assistant다.

규칙:
- 전세 계약, 보증금, 등기부등본, 특약, 임대차 절차, 일반적 법률 정보와 체크포인트 중심으로 답변한다.
- 위험도 자체를 최종 판정하거나 기존 분석 결과를 덮어쓰지 않는다.
- 법률 자문을 확정적으로 제공하지 않는다.
- 범위를 벗어난 일반 질문은 짧게 제한하고 전세/계약 관련 질문으로 유도한다.
- 답변은 한국어로 하고, 짧고 구조적으로 작성한다.
- 가능하면 바로 확인할 실무 체크포인트를 포함한다.
- 출처가 없으면 조문 번호나 판례를 지어내지 않는다.
""".strip()


class ChatbotService:
    def __init__(self) -> None:
        self._model_name = settings.openai_model

    def answer_question(
        self,
        question: str,
        history: list[ChatHistoryMessage],
        analysis: AnalysisDetailResponse | None = None,
    ) -> QaResponse:
        if not settings.openai_api_key or not settings.openai_api_key.strip():
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        model = ChatOpenAI(
            model=self._model_name,
            api_key=settings.openai_api_key,
            temperature=0.2,
        )

        messages = [SystemMessage(content=SYSTEM_PROMPT)]

        if analysis is not None:
            messages.append(
                SystemMessage(
                    content=(
                        "참고용 분석 컨텍스트:\n"
                        f"- analysis_id: {analysis.analysis_id}\n"
                        f"- overall_risk: {analysis.overall_risk}\n"
                        f"- explanation: {analysis.explanation}\n"
                        f"- risk_factors: {', '.join(f.title for f in analysis.risk_factors)}\n"
                        "이 컨텍스트는 참고용이며, 분석 결과를 재판정하지 말고 질문 이해에만 활용한다."
                    )
                )
            )

        for item in history:
            if item.role == "user":
                messages.append(HumanMessage(content=item.text))
            else:
                messages.append(AIMessage(content=item.text))

        messages.append(HumanMessage(content=question))
        result = model.invoke(messages)
        answer = result.content if isinstance(result.content, str) else str(result.content)

        references = ["AI generated guidance"]
        if analysis is not None:
            references.append("analysis context")

        return QaResponse(
            answer=answer.strip(),
            references=references,
            disclaimer=DISCLAIMER,
            scope=SCOPE,
        )
