from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import quote

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
OFFICIAL_LAW_BASE_URL = "https://www.law.go.kr/법령"
OFFICIAL_PRECEDENT_BASE_URL = "https://www.law.go.kr/precInfoP.do?precSeq="

# 재순위: 넓게 뽑아 LLM으로 다시 세운 뒤 top_k만 넣는다.
# eval/run_rag_configs.py에서 측정한 구성 그대로다 — 바꾸면 측정치가 무효가 된다.
RERANK_MODEL = "gpt-4.1-mini"
RERANK_POOL = 20
RERANK_EXCERPT = 600
PRECEDENT_FETCH_RATIO = 4  # 판례 1건이 여러 청크 → 후보 20건 확보용 여유

RERANK_PROMPT = """
너는 법률 질문에 답하는 RAG의 재순위기다.
질문과 검색 후보 목록을 받아, 질문에 답할 근거로서 쓸모 있는 순서로 다시 세운다.

기준:
- 질문이 묻는 쟁점을 직접 다루는 문서가 위다.
- 질문에 쓰인 단어가 들어 있다는 이유만으로 올리지 않는다. 쟁점이 맞아야 한다.
- 일반론보다 그 쟁점을 정면으로 판단한 것이 위다.

출력은 JSON 객체 하나다. 입력에 있는 번호를 하나도 빠짐없이, 좋은 순서대로 넣는다.
{"ranked": [번호, 번호, ...]}
""".strip()

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
답변은 Markdown으로 작성한다. 섹션 제목은 반드시 독립된 줄에 `## 제목`으로 쓰고, 제목 앞뒤에는 빈 줄을 둔다.
목록의 각 항목은 반드시 새 줄에서 `-` 또는 `1.`로 시작한다. 제목·목록·본문을 같은 줄에 이어 쓰지 않는다.
""".strip()

LEGAL_SYSTEM_PROMPT = """
당신은 한국 전세 계약 법령 질의응답 보조자다.
아래 제공된 출처(법령 조문과 판례)만 근거로 답변한다. 출처에 없는 조문 번호, 법령명, 사건번호는 만들지 않는다.
법령 조문은 규정 자체를, 판례는 그 규정이 실제 분쟁에서 어떻게 해석됐는지를 보여준다. 둘 다 있으면 조문을 먼저 들고 판례로 보충한다.
판례를 인용할 때는 사건번호(예: 대법원 2022다255126)를 함께 적는다. 주어진 판례가 질문의 사실관계와 다르면 그 차이를 밝힌다.
답변은 한국어로, 핵심 결론 -> 근거 -> 실무 체크포인트 순서로 간결하게 작성한다.
답변은 Markdown으로 작성한다. `## 핵심 결론`, `## 근거`, `## 실무 체크포인트`는 각각 독립된 줄에 쓰고, 제목 앞뒤에는 빈 줄을 둔다.
근거와 체크포인트의 각 항목은 반드시 새 줄에서 `-` 또는 `1.`로 시작한다. 제목·목록·본문을 같은 줄에 이어 쓰지 않는다.
출처가 부족하면 부족하다고 명시하고, 추정으로 단정하지 않는다.
""".strip()


class LegalSourceRecord(TypedDict, total=False):
    citation_label: str
    source_type: Literal["law_article", "precedent"]
    score: float | None
    excerpt: str | None
    content: str | None
    official_url: str | None
    # 법령 조문일 때만
    law_name: str | None
    jo_code: str | None
    article_number: str | None
    article_title: str | None
    # 판례일 때만
    precedent_id: str | None
    case_name: str | None
    case_number: str | None
    court: str | None
    decision_date: str | None
    decision_type: str | None
    section: str | None


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


def _build_official_law_url(law_name: str | None, article_number: str | None) -> str | None:
    if not law_name or not article_number:
        return None
    return f"{OFFICIAL_LAW_BASE_URL}/{quote(law_name.strip(), safe='')}/{quote(article_number.strip(), safe='')}"


def _build_official_precedent_url(precedent_id: str | None) -> str | None:
    if not precedent_id or not precedent_id.isdigit():
        return None
    return f"{OFFICIAL_PRECEDENT_BASE_URL}{quote(precedent_id, safe='')}"


def _excerpt(value: str, limit: int = 280) -> str:
    text = _clean_text(value)
    return text[:limit].rstrip() + "..." if len(text) > limit else text


def _strip_law_header(page_content: str) -> str:
    """법령 조문 앞에 붙은 머리말(법령명~조문제목)을 걷어내고 본문만 남긴다.

    머리말이 280자 발췌를 다 채워서 정작 조문 본문이 화면에도 LLM 컨텍스트에도 안 들어갔다.
    법령명·조문번호는 메타데이터로 따로 전달된다.
    """
    _, separator, body = page_content.partition("\n본문:")
    return body.lstrip("\n") if separator else page_content


def _strip_precedent_header(page_content: str) -> str:
    """판례 청크 앞에 붙은 머리말 4줄(판례/선고일/사건명/구분)을 발췌에서 걷어낸다.

    머리말은 검색용으로 붙인 것이라 그대로 발췌하면 화면에 같은 문구만 반복된다.
    """
    parts = page_content.split("\n", 4)
    if len(parts) == 5 and parts[3].startswith("구분:"):
        return parts[4]
    return page_content


class ChatbotService:
    def __init__(self) -> None:
        self._model_name = settings.openai_model
        self._reasoning_effort = settings.openai_reasoning_effort
        self._vector_db_path = self._resolve_path(settings.vector_db_path)
        self._precedent_vector_db_path = self._resolve_path(settings.precedent_vector_db_path)
        self._embedding_model = settings.vector_db_embedding_model
        self._top_k = settings.vector_db_top_k
        self._precedent_top_k = settings.vector_db_precedent_top_k
        self._vectorstore: FAISS | None = None
        self._precedent_vectorstore: FAISS | None = None
        self._graph = self._build_graph()

    @staticmethod
    def _resolve_path(raw: str) -> Path:
        path = Path(raw).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path

    def _build_model(self, temperature: float = 0.2) -> ChatOpenAI:
        if not settings.openai_api_key or not settings.openai_api_key.strip():
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        return ChatOpenAI(
            model=self._model_name,
            api_key=settings.openai_api_key,
            reasoning_effort=self._reasoning_effort,
            temperature=temperature,
        )

    def _load_vectorstore(self, index_path: Path) -> FAISS | None:
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
            self._vectorstore = self._load_vectorstore(self._vector_db_path)
        return self._vectorstore

    def _get_precedent_vectorstore(self) -> FAISS | None:
        if self._precedent_vectorstore is None:
            self._precedent_vectorstore = self._load_vectorstore(self._precedent_vector_db_path)
        return self._precedent_vectorstore

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

    def _search(self, vectorstore: FAISS, question: str, k: int) -> list:
        try:
            return vectorstore.similarity_search_with_score(question, k=k)
        except Exception:  # pragma: no cover - retrieval fallback
            LOGGER.exception("Vector similarity search failed for question=%r", question)
            return []

    def _rerank(self, question: str, candidates: list[tuple]) -> list[tuple]:
        """후보(label, doc, score)를 LLM으로 다시 세운다. 실패하면 벡터 순서를 그대로 쓴다."""
        if len(candidates) < 2:
            return candidates

        items = [
            {"번호": index, "문서": label, "내용": doc.page_content[-RERANK_EXCERPT:]}
            for index, (label, doc, _) in enumerate(candidates, start=1)
        ]
        payload = json.dumps({"질문": question, "후보": items}, ensure_ascii=False)

        try:
            model = ChatOpenAI(
                model=RERANK_MODEL,
                api_key=settings.openai_api_key,
                temperature=0,
                model_kwargs={"response_format": {"type": "json_object"}},
            )
            response = model.invoke(
                [SystemMessage(content=RERANK_PROMPT), HumanMessage(content=payload)]
            )
            ranked = json.loads(response.content)["ranked"]
        except Exception:  # pragma: no cover - 재순위 실패는 검색 실패가 아니다
            LOGGER.exception("Rerank failed for question=%r; keeping vector order", question)
            return candidates

        picked, used = [], set()
        for number in ranked:
            if isinstance(number, int) and 1 <= number <= len(candidates) and number not in used:
                used.add(number)
                picked.append(candidates[number - 1])
        # 모델이 빠뜨린 후보는 원래 순서로 뒤에 채운다
        picked += [item for index, item in enumerate(candidates, start=1) if index not in used]
        return picked

    def _retrieve_law_sources(self, question: str) -> list[LegalSourceRecord]:
        vectorstore = self._get_vectorstore()
        if vectorstore is None:
            return []

        candidates: list[tuple] = []
        seen_labels: set[str] = set()

        for doc, score in self._search(vectorstore, question, RERANK_POOL):
            metadata = doc.metadata or {}
            citation_label = _clean_text(metadata.get("citation_label")) or _clean_text(
                f"{metadata.get('law_name', '')} {metadata.get('article_number') or metadata.get('jo_code') or ''}"
            )
            if not citation_label or citation_label in seen_labels:
                continue

            seen_labels.add(citation_label)
            candidates.append((citation_label, doc, score))

        sources: list[LegalSourceRecord] = []
        for citation_label, doc, score in self._rerank(question, candidates)[: self._top_k]:
            metadata = doc.metadata or {}
            body = _strip_law_header(doc.page_content)

            sources.append(
                {
                    "citation_label": citation_label,
                    "source_type": "law_article",
                    "law_name": _clean_text(metadata.get("law_name")) or citation_label,
                    "jo_code": metadata.get("jo_code"),
                    "article_number": metadata.get("article_number"),
                    "article_title": metadata.get("article_title"),
                    "score": float(score) if score is not None else None,
                    "excerpt": _excerpt(body),
                    "content": body,
                    "official_url": _build_official_law_url(
                        metadata.get("law_name"),
                        metadata.get("article_number") or metadata.get("jo_code"),
                    ),
                }
            )

        return sources

    def _retrieve_precedent_sources(self, question: str) -> list[LegalSourceRecord]:
        """판례는 한 건이 여러 청크라, 넉넉히 꺼내 판례 단위로 묶고 재순위 후 상위 N건만 남긴다."""
        vectorstore = self._get_precedent_vectorstore()
        if vectorstore is None:
            return []

        candidates: list[tuple] = []
        seen_ids: set[str] = set()

        for doc, score in self._search(vectorstore, question, RERANK_POOL * PRECEDENT_FETCH_RATIO):
            if len(candidates) >= RERANK_POOL:
                break

            metadata = doc.metadata or {}
            precedent_id = metadata.get("precedent_id")
            if not precedent_id or precedent_id in seen_ids:
                continue

            citation_label = _clean_text(metadata.get("citation_label"))
            if not citation_label:
                continue

            seen_ids.add(precedent_id)
            candidates.append((citation_label, doc, score))

        sources: list[LegalSourceRecord] = []
        for citation_label, doc, score in self._rerank(question, candidates)[: self._precedent_top_k]:
            metadata = doc.metadata or {}
            precedent_id = metadata.get("precedent_id")
            body = _strip_precedent_header(doc.page_content)

            sources.append(
                {
                    "citation_label": citation_label,
                    "source_type": "precedent",
                    "precedent_id": precedent_id,
                    "case_name": _clean_text(metadata.get("case_name")) or None,
                    "case_number": _clean_text(metadata.get("case_number")) or None,
                    "court": _clean_text(metadata.get("court")) or None,
                    "decision_date": _clean_text(metadata.get("decision_date")) or None,
                    "decision_type": _clean_text(metadata.get("decision_type")) or None,
                    "section": _clean_text(metadata.get("section")) or None,
                    "score": float(score) if score is not None else None,
                    "excerpt": _excerpt(body),
                    "content": body,
                    "official_url": _build_official_precedent_url(precedent_id),
                }
            )

        return sources

    def _retrieve_legal_sources(self, question: str) -> list[LegalSourceRecord]:
        return self._retrieve_law_sources(question) + self._retrieve_precedent_sources(question)

    def _retrieve_legal_sources_node(self, state: QaState) -> QaState:
        return {"sources": self._retrieve_legal_sources(state["question"])}

    def _build_legal_context(self, sources: list[LegalSourceRecord]) -> str:
        if not sources:
            return "검색된 법령 출처가 없습니다. 부족한 근거는 추측하지 말고, 문서 부족을 명시한다."

        blocks: list[str] = []
        for index, source in enumerate(sources, start=1):
            lines = [f"[{index}] {source['citation_label']}"]

            if source.get("source_type") == "precedent":
                lines.append("종류: 판례")
                if source.get("case_name"):
                    lines.append(f"사건명: {source['case_name']}")
                decided = " ".join(filter(None, [source.get("court"), source.get("decision_date")]))
                if decided:
                    lines.append(f"선고: {decided}")
                if source.get("section"):
                    lines.append(f"해당 부분: {source['section']}")
            else:
                lines.append("종류: 법령 조문")
                lines.append(f"법령명: {source['law_name']}")
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
            extra_system_messages=[f"검색된 출처(법령 조문·판례):\n{legal_context}"],
        )
        result = model.invoke(messages)
        answer = result.content if isinstance(result.content, str) else str(result.content)

        references = [source["citation_label"] for source in sources]
        return {
            "answer": answer.strip(),
            "references": references,
            "sources": sources,
        }

    async def stream_answer_question(
        self,
        question: str,
        history: list[ChatHistoryMessage],
        analysis: AnalysisDetailResponse | None = None,
    ) -> AsyncIterator[tuple[Literal["token", "done"], dict]]:
        if not settings.openai_api_key or not settings.openai_api_key.strip():
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        route, _ = self._classify_question(question)
        sources: list[LegalSourceRecord] = []
        system_prompt = SIMPLE_SYSTEM_PROMPT
        extra_system_messages = None

        if route == "legal":
            sources = self._retrieve_legal_sources(question)
            if not sources:
                answer = "관련 법령 문서를 충분히 찾지 못했습니다. 질문을 조금 더 구체적으로 적어 주시면 해당 법령을 다시 찾아볼 수 있습니다."
                yield "token", {"text": answer}
                yield "done", {
                    "references": [],
                    "disclaimer": DISCLAIMER,
                    "scope": SCOPE,
                    "route": route,
                    "sources": [],
                }
                return

            system_prompt = LEGAL_SYSTEM_PROMPT
            extra_system_messages = [f"검색된 출처(법령 조문·판례):\n{self._build_legal_context(sources)}"]

        model = self._build_model()
        messages = _build_messages(
            question=question,
            history=history,
            analysis=analysis,
            system_prompt=system_prompt,
            extra_system_messages=extra_system_messages,
        )

        async for chunk in model.astream(messages):
            text = chunk.content if isinstance(chunk.content, str) else ""
            if text:
                yield "token", {"text": text}

        references = [source["citation_label"] for source in sources]
        if route == "simple":
            references = ["AI generated guidance"]
            if analysis is not None:
                references.append("analysis context")

        yield "done", {
            "references": references,
            "disclaimer": DISCLAIMER,
            "scope": SCOPE,
            "route": route,
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
