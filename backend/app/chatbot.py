from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.constants import END, START
from langgraph.graph.state import StateGraph

try:
    from langchain_community.vectorstores import FAISS
except ImportError:  # pragma: no cover - fallback for older LangChain installs
    from langchain.vectorstores import FAISS

from .schemas import AnalysisDetailResponse, ChatHistoryMessage, LegalSource, QaResponse
from .settings import settings

LOGGER = logging.getLogger(__name__)

DISCLAIMER = "이 답변은 참고용 정보이며, 구체적 사실관계에 따라 달라질 수 있으므로 법률 전문가 상담이 필요할 수 있습니다."
SCOPE = "jeonse-legal-assistant"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VECTOR_DB_PATH = Path(__file__).resolve().parents[2] / "vectorDB" / "laws_faiss"

CASUAL_HINTS = (
    "이름이 뭐",
    "네 이름",
    "너 누구",
    "누구야",
    "안녕",
    "hello",
    "hi",
)

LEGAL_HINTS = (
    "전세",
    "임대차",
    "보증금",
    "등기",
    "등기부",
    "근저당",
    "확정일자",
    "전입신고",
    "임차",
    "임대",
    "계약",
    "특약",
    "공인중개사",
    "부동산",
    "주택",
    "상가",
    "건축",
    "불법",
    "위법",
    "소송",
    "판례",
    "조문",
    "법령",
    "경매",
    "경락",
    "우선변제",
    "대항력",
    "가압류",
    "가처분",
    "세금",
    "취득세",
    "재산세",
)

SIMPLE_SYSTEM_PROMPT = """
당신은 전세 리스크 보조 챗봇이다.
현재 질문은 일반 대화 또는 단순 안내로 판단되었으므로, 법령 검색이나 인용 없이 짧고 자연스럽게 답한다.
질문이 법률 상담에 가깝다면 전세, 임대차, 등기 관련 질문으로 이어가도록 유도한다.
답변은 한국어로 하고, 과도하게 길게 쓰지 않는다.
""".strip()

LEGAL_SYSTEM_PROMPT = """
당신은 한국 전세 계약 법령 질의응답 보조자다.
아래 제공된 법령 출처만 근거로 답변한다. 출처에 없는 조문 번호, 법령명, 판례는 만들지 않는다.
답변은 한국어로, 핵심 결론 -> 근거 -> 실무 체크포인트 순서로 간결하게 작성한다.
출처가 부족하면 부족하다고 명시하고, 추정으로 단정하지 않는다.
""".strip()


class LegalSourceRecord(TypedDict, total=False):
    citation_label: str
    law_name: str
    jo_code: str | None
    article_number: str | None
    article_title: str | None
    score: float | None
    excerpt: str | None


class QaState(TypedDict, total=False):
    question: str
    history: list[ChatHistoryMessage]
    analysis: AnalysisDetailResponse | None
    route: Literal["simple", "legal"]
    route_reason: str
    answer: str
    references: list[str]
    sources: list[LegalSourceRecord]


def _format_analysis_context(analysis: AnalysisDetailResponse | None) -> str | None:
    if analysis is None:
        return None

    risk_factor_titles = ", ".join(f.title for f in analysis.risk_factors) or "없음"
    return (
        "참고용 분석 컨텍스트:\n"
        f"- analysis_id: {analysis.analysis_id}\n"
        f"- overall_risk: {analysis.overall_risk}\n"
        f"- explanation: {analysis.explanation}\n"
        f"- risk_factors: {risk_factor_titles}\n"
        "이 컨텍스트는 참고용이며, 분석 결과를 재판정하지 말고 질문 이해에만 활용한다."
    )


def _build_messages(
    question: str,
    history: list[ChatHistoryMessage],
    analysis: AnalysisDetailResponse | None,
    system_prompt: str,
    extra_system_messages: list[str] | None = None,
) -> list[BaseMessage]:
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]

    analysis_context = _format_analysis_context(analysis)
    if analysis_context:
        messages.append(SystemMessage(content=analysis_context))

    for text in extra_system_messages or []:
        messages.append(SystemMessage(content=text))

    for item in history:
        if item.role == "user":
            messages.append(HumanMessage(content=item.text))
        else:
            messages.append(AIMessage(content=item.text))

    messages.append(HumanMessage(content=question))
    return messages


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split()).strip()


class ChatbotService:
    def __init__(self) -> None:
        self._model_name = settings.openai_model
        vector_db_path = Path(settings.vector_db_path).expanduser()
        self._vector_db_path = vector_db_path if vector_db_path.is_absolute() else PROJECT_ROOT / vector_db_path
        self._embedding_model = settings.vector_db_embedding_model
        self._top_k = settings.vector_db_top_k
        self._vectorstore: FAISS | None = None
        self._graph = self._build_graph()

    def _build_model(self, temperature: float = 0.2) -> ChatOpenAI:
        if not settings.openai_api_key or not settings.openai_api_key.strip():
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        return ChatOpenAI(
            model=self._model_name,
            api_key=settings.openai_api_key,
            temperature=temperature,
        )

    def _load_vectorstore(self) -> FAISS | None:
        index_path = self._vector_db_path
        required_files = [index_path / "index.faiss", index_path / "index.pkl"]
        if not all(path.exists() for path in required_files):
            LOGGER.warning("Vector DB not found at %s; legal QA will fall back to empty sources.", index_path)
            return None

        try:
            embeddings = OpenAIEmbeddings(
                model=self._embedding_model,
                api_key=settings.openai_api_key,
            )
            return FAISS.load_local(
                str(index_path),
                embeddings,
                allow_dangerous_deserialization=True,
            )
        except Exception:  # pragma: no cover - load-time safety fallback
            LOGGER.exception("Failed to load vector DB from %s", index_path)
            return None

    def _get_vectorstore(self) -> FAISS | None:
        if self._vectorstore is None:
            self._vectorstore = self._load_vectorstore()
        return self._vectorstore

    def _build_graph(self):
        graph = StateGraph(QaState)
        graph.add_node("classify_question", self._classify_question_node)
        graph.add_node("simple_answer", self._simple_answer_node)
        graph.add_node("retrieve_legal_sources", self._retrieve_legal_sources_node)
        graph.add_node("legal_answer", self._legal_answer_node)

        graph.add_edge(START, "classify_question")
        graph.add_conditional_edges(
            "classify_question",
            self._route_after_classification,
            {
                "simple": "simple_answer",
                "legal": "retrieve_legal_sources",
            },
        )
        graph.add_edge("simple_answer", END)
        graph.add_edge("retrieve_legal_sources", "legal_answer")
        graph.add_edge("legal_answer", END)
        return graph.compile()

    def _classify_question(self, question: str) -> tuple[Literal["simple", "legal"], str]:
        normalized = re.sub(r"\s+", "", question.lower())
        raw = question.lower()

        if any(hint in normalized or hint in raw for hint in LEGAL_HINTS):
            return "legal", "legal keyword"

        if any(hint.replace(" ", "") in normalized or hint in raw for hint in CASUAL_HINTS):
            return "simple", "casual"

        if "?" in question:
            return "simple", "default question"

        return "simple", "default simple"

    def _classify_question_node(self, state: QaState) -> QaState:
        route, reason = self._classify_question(state["question"])
        return {"route": route, "route_reason": reason}

    def _route_after_classification(self, state: QaState) -> str:
        return state["route"]

    def _simple_answer_node(self, state: QaState) -> QaState:
        model = self._build_model()
        messages = _build_messages(
            question=state["question"],
            history=state.get("history", []),
            analysis=state.get("analysis"),
            system_prompt=SIMPLE_SYSTEM_PROMPT,
        )
        result = model.invoke(messages)
        answer = result.content if isinstance(result.content, str) else str(result.content)

        references = ["AI generated guidance"]
        if state.get("analysis") is not None:
            references.append("analysis context")

        return {
            "answer": answer.strip(),
            "references": references,
            "sources": [],
        }

    def _retrieve_legal_sources(self, question: str) -> list[LegalSourceRecord]:
        vectorstore = self._get_vectorstore()
        if vectorstore is None:
            return []

        try:
            results = vectorstore.similarity_search_with_score(question, k=self._top_k)
        except Exception:  # pragma: no cover - retrieval fallback
            LOGGER.exception("Vector similarity search failed for question=%r", question)
            return []

        sources: list[LegalSourceRecord] = []
        seen_labels: set[str] = set()

        for doc, score in results:
            metadata = doc.metadata or {}
            citation_label = _clean_text(metadata.get("citation_label")) or _clean_text(
                f"{metadata.get('law_name', '')} {metadata.get('article_number') or metadata.get('jo_code') or ''}"
            )
            if not citation_label or citation_label in seen_labels:
                continue

            seen_labels.add(citation_label)
            excerpt = _clean_text(doc.page_content)
            if len(excerpt) > 280:
                excerpt = excerpt[:280].rstrip() + "..."

            sources.append(
                {
                    "citation_label": citation_label,
                    "law_name": _clean_text(metadata.get("law_name")) or citation_label,
                    "jo_code": metadata.get("jo_code"),
                    "article_number": metadata.get("article_number"),
                    "article_title": metadata.get("article_title"),
                    "score": float(score) if score is not None else None,
                    "excerpt": excerpt,
                }
            )

        return sources

    def _retrieve_legal_sources_node(self, state: QaState) -> QaState:
        return {"sources": self._retrieve_legal_sources(state["question"])}

    def _build_legal_context(self, sources: list[LegalSourceRecord]) -> str:
        if not sources:
            return "검색된 법령 출처가 없습니다. 부족한 근거는 추측하지 말고, 문서 부족을 명시한다."

        blocks: list[str] = []
        for index, source in enumerate(sources, start=1):
            lines = [
                f"[{index}] {source['citation_label']}",
                f"법령명: {source['law_name']}",
            ]
            if source.get("article_title"):
                lines.append(f"조문제목: {source['article_title']}")
            if source.get("excerpt"):
                lines.append(f"본문 발췌: {source['excerpt']}")
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    def _legal_answer_node(self, state: QaState) -> QaState:
        sources = state.get("sources", [])
        if not sources:
            return {
                "answer": (
                    "관련 법령 문서를 충분히 찾지 못했습니다. 질문을 조금 더 구체적으로 적어 주시면 "
                    "해당 법령을 다시 찾아볼 수 있습니다."
                ),
                "references": [],
                "sources": [],
            }

        model = self._build_model()
        legal_context = self._build_legal_context(sources)
        messages = _build_messages(
            question=state["question"],
            history=state.get("history", []),
            analysis=state.get("analysis"),
            system_prompt=LEGAL_SYSTEM_PROMPT,
            extra_system_messages=[f"법령 출처:\n{legal_context}"],
        )
        result = model.invoke(messages)
        answer = result.content if isinstance(result.content, str) else str(result.content)

        references = [source["citation_label"] for source in sources]
        return {
            "answer": answer.strip(),
            "references": references,
            "sources": sources,
        }

    def answer_question(
        self,
        question: str,
        history: list[ChatHistoryMessage],
        analysis: AnalysisDetailResponse | None = None,
    ) -> QaResponse:
        if not settings.openai_api_key or not settings.openai_api_key.strip():
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        result: QaState = self._graph.invoke(
            {
                "question": question,
                "history": history,
                "analysis": analysis,
                "references": [],
                "sources": [],
            }
        )

        return QaResponse(
            answer=result["answer"].strip(),
            references=result.get("references", []),
            disclaimer=DISCLAIMER,
            scope=SCOPE,
            route=result.get("route", "simple"),
            sources=[LegalSource(**source) for source in result.get("sources", [])],
        )
