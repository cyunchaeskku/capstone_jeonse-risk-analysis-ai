import { useState } from 'react';
import { useChatbot } from '../context/ChatbotContext';
import ChatbotPanel from '../ui/ChatbotPanel';

const suggestedQuestions = [
  '전세계약 전 꼭 확인할 사항은 무엇인가요?',
  '임대인이 보증금을 돌려주지 않으면 어떻게 해야 하나요?',
  '등기부등본에서 위험 신호는 무엇인가요?',
];

function SourceDetailCard({ source, onClose }) {
  const isPrecedent = source.source_type === 'precedent';

  return (
    <section className="rounded-2xl border border-coral/20 bg-white/90 p-4 shadow-[0_18px_40px_rgba(18,70,51,0.1)]">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-semibold tracking-[0.14em] text-coral uppercase">
          {isPrecedent ? '판례 상세' : '문서 상세'}
        </p>
        <button
          type="button"
          onClick={onClose}
          aria-label="문서 상세 닫기"
          className="rounded-full px-2 py-1 text-sm text-slate-400 transition hover:bg-sand hover:text-ink"
        >
          ×
        </button>
      </div>
      <h2 className="mt-2 text-base font-semibold leading-6 text-slate-800">{source.citation_label}</h2>
      {isPrecedent ? (
        <>
          {source.case_name ? <p className="mt-1 text-sm text-slate-500">{source.case_name}</p> : null}
          <dl className="mt-4 space-y-2 text-xs leading-5 text-slate-600">
            {source.case_number ? (
              <div>
                <dt className="font-medium text-slate-700">사건번호</dt>
                <dd>{source.case_number}</dd>
              </div>
            ) : null}
            {source.court ? (
              <div>
                <dt className="font-medium text-slate-700">선고법원</dt>
                <dd>{source.court}</dd>
              </div>
            ) : null}
            {source.decision_date ? (
              <div>
                <dt className="font-medium text-slate-700">선고일</dt>
                <dd>{source.decision_date}</dd>
              </div>
            ) : null}
            {source.decision_type ? (
              <div>
                <dt className="font-medium text-slate-700">판결유형</dt>
                <dd>{source.decision_type}</dd>
              </div>
            ) : null}
          </dl>
        </>
      ) : (
        <>
          {source.article_title ? <p className="mt-1 text-sm text-slate-500">{source.article_title}</p> : null}
          <dl className="mt-4 space-y-2 text-xs leading-5 text-slate-600">
            <div>
              <dt className="font-medium text-slate-700">법령명</dt>
              <dd>{source.law_name}</dd>
            </div>
            {source.article_number || source.jo_code ? (
              <div>
                <dt className="font-medium text-slate-700">조문번호</dt>
                <dd>{source.article_number ?? source.jo_code}</dd>
              </div>
            ) : null}
          </dl>
        </>
      )}
      {isPrecedent ? (
        <p className="mt-4 text-xs font-medium text-slate-700">
          검색된 판례 내용{source.section ? ` · ${source.section}` : ''}
        </p>
      ) : null}
      <div
        className={`${isPrecedent ? 'mt-2' : 'mt-4'} max-h-72 overflow-y-auto rounded-xl bg-sand/70 p-3 text-xs leading-6 whitespace-pre-wrap text-slate-600 lg:max-h-[calc(100vh-24rem)]`}
      >
        {source.content ?? source.excerpt ?? '표시할 문서 본문이 없습니다.'}
      </div>
      {source.official_url ? (
        <a
          href={source.official_url}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-coral transition hover:text-ink"
        >
          {isPrecedent ? '국가법령정보센터 판례 원문 보기' : '국가법령정보센터 현행 법령 보기'}{' '}
          <span aria-hidden="true">↗</span>
        </a>
      ) : null}
    </section>
  );
}

function ChatbotPage() {
  const [selectedSource, setSelectedSource] = useState(null);
  const { setDraftMessage } = useChatbot();

  return (
    <main className="mx-auto grid min-h-[calc(100vh-72px)] w-full max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[20rem_minmax(0,1fr)] lg:py-8">
      <aside className="lg:sticky lg:top-8 lg:self-start">
        {selectedSource ? (
          <SourceDetailCard source={selectedSource} onClose={() => setSelectedSource(null)} />
        ) : (
          <>
            <h1 className="text-2xl font-semibold text-ink sm:text-3xl">전세 리스크 챗봇</h1>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              더 넓은 화면에서 질문하고, 이전 대화 맥락을 이어서 답변을 받을 수 있습니다.
            </p>
            <div className="mt-7">
              <p className="text-xs font-semibold tracking-[0.14em] text-coral uppercase">추천 질문</p>
              <div className="mt-3 space-y-2">
                {suggestedQuestions.map((question) => (
                  <button
                    key={question}
                    type="button"
                    onClick={() => setDraftMessage(question)}
                    className="w-full rounded-xl border border-slate-200 bg-white/75 px-3 py-2 text-left text-sm leading-5 text-slate-600 transition hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-coral/40"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </aside>
      <ChatbotPanel
        className="h-[calc(100vh-196px)] min-h-[36rem] lg:h-[calc(100vh-136px)]"
        description="더 넓은 화면에서 질문하고, 이전 대화 맥락을 이어서 답변을 받을 수 있습니다."
        onSelectSource={setSelectedSource}
      />
    </main>
  );
}

export default ChatbotPage;
