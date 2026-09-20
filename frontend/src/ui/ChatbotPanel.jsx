import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { useChatbot } from '../context/ChatbotContext';

const markdownComponents = {
  h1: ({ children }) => <h1 className="mt-5 text-xl font-semibold text-slate-900 first:mt-0">{children}</h1>,
  h2: ({ children }) => (
    <h2
      className={`mt-5 text-lg font-semibold text-slate-900 first:mt-0 ${
        children === '핵심 결론' ? 'rounded-lg bg-coral/15 px-3 py-2' : ''
      }`}
    >
      {children}
    </h2>
  ),
  h3: ({ children }) => <h3 className="mt-4 font-semibold text-slate-800 first:mt-0">{children}</h3>,
  p: ({ children }) => <p className="mt-3 first:mt-0">{children}</p>,
  ul: ({ children }) => <ul className="mt-3 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mt-3 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
};

function ChatMessageText({ message }) {
  if (message.role !== 'assistant' || message.isError) {
    return <p className="whitespace-pre-wrap">{message.text}</p>;
  }

  return <ReactMarkdown components={markdownComponents}>{message.text}</ReactMarkdown>;
}

function SourceCard({ source, onSelectSource }) {
  const isPrecedent = source.source_type === 'precedent';
  // 판례는 사건명이, 법령은 조문제목이 인용 라벨 아래 부제로 들어간다.
  const subtitle = isPrecedent ? source.case_name : source.article_title;

  const content = (
    <>
      <p className="flex items-center gap-1.5 font-medium text-slate-700">
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
            isPrecedent ? 'bg-amber-100 text-amber-700' : 'bg-slate-200 text-slate-600'
          }`}
        >
          {isPrecedent ? '판례' : '법령'}
        </span>
        <span>{source.citation_label}</span>
      </p>
      {subtitle ? <p className="mt-0.5 line-clamp-2 text-slate-500">{subtitle}</p> : null}
      {isPrecedent && source.section ? (
        <p className="mt-0.5 text-[10px] text-slate-400">{source.section}</p>
      ) : null}
      {source.excerpt ? <p className="mt-1 whitespace-pre-wrap text-slate-500">{source.excerpt}</p> : null}
    </>
  );

  if (!onSelectSource) {
    return <div className="rounded-xl bg-white/75 px-3 py-2 text-[11px] leading-5 text-slate-600">{content}</div>;
  }

  return (
    <button
      type="button"
      onClick={() => onSelectSource(source)}
      className="w-full cursor-pointer rounded-xl bg-white/75 px-3 py-2 text-left text-[11px] leading-5 text-slate-600 transition hover:bg-slate-100 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-coral/40"
    >
      {content}
      <span className="mt-2 block font-medium text-coral">문서 상세 보기</span>
    </button>
  );
}

function ChatbotPanel({
  className = '',
  description,
  onRequestClose,
  onRequestFullscreen,
  onSelectSource,
  showFullscreenButton = false,
  showCloseButton = false,
}) {
  const {
    activeAnalysis,
    clearActiveAnalysis,
    draftMessage,
    error,
    isSending,
    messages,
    resetChat,
    sendMessage,
    setDraftMessage,
  } = useChatbot();
  const inputRef = useRef(null);
  const [expandedSourceMessageIds, setExpandedSourceMessageIds] = useState(new Set());

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = (event) => {
    event.preventDefault();
    sendMessage();
  };

  const handleKeyDown = (event) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }

    event.preventDefault();
    sendMessage();
  };

  const toggleSources = (messageId) => {
    setExpandedSourceMessageIds((current) => {
      const next = new Set(current);
      if (next.has(messageId)) {
        next.delete(messageId);
      } else {
        next.add(messageId);
      }
      return next;
    });
  };

  return (
    <section
      className={`flex w-full flex-col overflow-hidden rounded-2xl border border-white/80 bg-white/95 shadow-[0_28px_80px_rgba(18,70,51,0.18)] backdrop-blur ${className}`}
    >
      <header className="flex items-center justify-between border-b border-coral/15 bg-sand px-5 py-4">
        <div>
          <p className="text-sm font-semibold tracking-[0.18em] text-coral uppercase">Legal Assistant</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">전세 리스크 챗봇</h2>
          {description ? <p className="mt-1 text-xs text-slate-500">{description}</p> : null}
        </div>
        <div className="flex items-center gap-2">
          {messages.length > 1 ? (
            <button
              type="button"
              onClick={resetChat}
              className="rounded-full border border-coral/20 px-3 py-1 text-sm font-medium text-slate-600 transition hover:border-coral/40 hover:text-ink"
            >
              새 대화
            </button>
          ) : null}
          {showFullscreenButton ? (
            <button
              type="button"
              onClick={onRequestFullscreen}
              className="rounded-full border border-coral/20 px-3 py-1 text-sm font-medium text-slate-600 transition hover:border-coral/40 hover:text-ink"
            >
              전체화면
            </button>
          ) : null}
          {showCloseButton ? (
            <button
              type="button"
              aria-label="챗봇 닫기"
              onClick={onRequestClose}
              className="rounded-full border border-coral/20 px-3 py-1 text-sm font-medium text-slate-600 transition hover:border-coral/40 hover:text-ink"
            >
              닫기
            </button>
          ) : null}
        </div>
      </header>

      {activeAnalysis ? (
        <div className="flex items-center justify-between gap-3 border-b border-coral/15 bg-coral/5 px-5 py-3">
          <p className="text-xs text-slate-600">
            <span className="font-medium text-slate-900">{activeAnalysis.listingName}</span> 분석 결과를
            근거로 답변합니다.
          </p>
          <button
            type="button"
            onClick={clearActiveAnalysis}
            className="shrink-0 text-xs font-medium text-slate-500 transition hover:text-coral"
          >
            해제
          </button>
        </div>
      ) : null}

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.map((message) => (
          <article key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                message.role === 'user'
                  ? 'rounded-br-md bg-ink text-white'
                  : message.isError
                    ? 'rounded-bl-md bg-red-50 text-red-700'
                    : 'rounded-bl-md bg-slate-100 text-slate-700'
              }`}
            >
              <ChatMessageText message={message} />
              <p
                className={`mt-2 text-[11px] ${
                  message.role === 'user' ? 'text-slate-300' : 'text-slate-400'
                }`}
              >
                {message.timestamp}
              </p>
              {message.role === 'assistant' && Array.isArray(message.sources) && message.sources.length > 0 ? (
                <div className="mt-3 space-y-2 border-t border-white/50 pt-3">
                  <button
                    type="button"
                    onClick={() => toggleSources(message.id)}
                    aria-expanded={expandedSourceMessageIds.has(message.id)}
                    className="text-[11px] font-semibold tracking-[0.14em] text-slate-500 uppercase transition hover:text-slate-700"
                  >
                    {expandedSourceMessageIds.has(message.id)
                      ? '출처 문서 접기'
                      : `출처 문서 ${message.sources.length}개 보기`}
                  </button>
                  {expandedSourceMessageIds.has(message.id) ? (
                    <div className="space-y-2">
                      {message.sources.map((source) => (
                        <SourceCard
                          key={`${source.citation_label}-${source.precedent_id ?? source.article_number ?? source.jo_code ?? 'source'}`}
                          source={source}
                          onSelectSource={onSelectSource}
                        />
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </article>
        ))}
        {isSending ? (
          <article className="flex justify-start">
            <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-coral/10 px-4 py-3 text-sm leading-6 text-slate-700">
              <p>응답을 생성하는 중입니다...</p>
              <p className="mt-2 text-[11px] text-slate-400">잠시만 기다려주세요</p>
            </div>
          </article>
        ) : null}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-coral/15 bg-white px-4 py-3">
        <label htmlFor="chatbot-message" className="sr-only">
          챗봇 메시지 입력
        </label>
        <div className="rounded-xl border border-coral/15 bg-sand p-2">
          <textarea
            id="chatbot-message"
            ref={inputRef}
            rows="2"
            value={draftMessage}
            onChange={(event) => setDraftMessage(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="등기부등본이나 계약 전 체크포인트에 대해 질문해보세요."
            className="w-full resize-none bg-transparent px-3 py-1.5 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400"
          />
          <div className="flex items-center justify-between px-2 pb-1 pt-1">
            <p className="text-xs text-slate-400">
              {error
                ? '일시적인 오류가 있었습니다. 다시 시도할 수 있습니다.'
                : 'Enter 전송 · Shift+Enter 줄바꿈'}
            </p>
            <button
              type="submit"
              disabled={isSending}
              className="rounded-full bg-coral px-4 py-2 text-sm font-semibold text-ink transition hover:bg-[#a9dc63] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSending ? '전송 중...' : '전송'}
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}

export default ChatbotPanel;
