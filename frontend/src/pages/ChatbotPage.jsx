import { useState } from 'react';
import ChatbotPanel from '../ui/ChatbotPanel';

function SourceDetailCard({ source, onClose }) {
  return (
    <section className="mt-6 rounded-3xl border border-coral/20 bg-white/90 p-4 shadow-[0_18px_40px_rgba(18,70,51,0.1)]">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-semibold tracking-[0.14em] text-coral uppercase">문서 상세</p>
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
      <div className="mt-4 max-h-72 overflow-y-auto rounded-2xl bg-sand/70 p-3 text-xs leading-6 whitespace-pre-wrap text-slate-600 lg:max-h-[calc(100vh-24rem)]">
        {source.content ?? source.excerpt ?? '표시할 문서 본문이 없습니다.'}
      </div>
    </section>
  );
}

function ChatbotPage() {
  const [selectedSource, setSelectedSource] = useState(null);

  return (
    <main className="mx-auto grid min-h-[calc(100vh-72px)] w-full max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[20rem_minmax(0,1fr)] lg:py-8">
      <aside className="lg:sticky lg:top-8 lg:self-start">
        <h1 className="text-2xl font-semibold text-ink sm:text-3xl">전세 리스크 챗봇</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          더 넓은 화면에서 질문하고, 이전 대화 맥락을 이어서 답변을 받을 수 있습니다.
        </p>
        {selectedSource ? <SourceDetailCard source={selectedSource} onClose={() => setSelectedSource(null)} /> : null}
      </aside>
      <ChatbotPanel
        className="h-[calc(100vh-196px)] min-h-[36rem] lg:h-[calc(100vh-136px)]"
        onSelectSource={setSelectedSource}
      />
    </main>
  );
}

export default ChatbotPage;
