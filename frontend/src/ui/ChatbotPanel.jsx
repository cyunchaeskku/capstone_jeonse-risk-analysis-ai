import { useEffect, useRef } from 'react';
import { useChatbot } from '../context/ChatbotContext';

function ChatbotPanel({
  className = '',
  onRequestClose,
  onRequestFullscreen,
  showFullscreenButton = false,
  showCloseButton = false,
}) {
  const { draftMessage, error, isSending, messages, sendMessage, setDraftMessage } = useChatbot();
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = (event) => {
    event.preventDefault();
    sendMessage();
  };

  return (
    <section
      className={`flex w-full flex-col overflow-hidden rounded-[1.75rem] border border-white/80 bg-white/95 shadow-[0_28px_80px_rgba(18,70,51,0.18)] backdrop-blur ${className}`}
    >
      <header className="flex items-center justify-between border-b border-coral/15 bg-sand px-5 py-4">
        <div>
          <p className="text-sm font-semibold tracking-[0.18em] text-coral uppercase">Legal Assistant</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">전세 리스크 챗봇</h2>
        </div>
        <div className="flex items-center gap-2">
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

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.map((message) => (
          <article key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-3xl px-4 py-3 text-sm leading-6 ${
                message.role === 'user'
                  ? 'rounded-br-md bg-ink text-white'
                  : message.isError
                    ? 'rounded-bl-md bg-red-50 text-red-700'
                    : 'rounded-bl-md bg-coral/10 text-slate-700'
              }`}
            >
              <p>{message.text}</p>
              <p
                className={`mt-2 text-[11px] ${
                  message.role === 'user' ? 'text-slate-300' : 'text-slate-400'
                }`}
              >
                {message.timestamp}
              </p>
              {message.role === 'assistant' && Array.isArray(message.sources) && message.sources.length > 0 ? (
                <div className="mt-3 space-y-2 border-t border-white/50 pt-3">
                  <p className="text-[11px] font-semibold tracking-[0.14em] text-slate-500 uppercase">
                    출처 문서
                  </p>
                  <div className="space-y-2">
                    {message.sources.map((source) => (
                      <div key={`${source.citation_label}-${source.article_number ?? source.jo_code ?? 'source'}`} className="rounded-2xl bg-white/75 px-3 py-2 text-[11px] leading-5 text-slate-600">
                        <p className="font-medium text-slate-700">{source.citation_label}</p>
                        {source.article_title ? (
                          <p className="mt-0.5 text-slate-500">{source.article_title}</p>
                        ) : null}
                        {source.excerpt ? (
                          <p className="mt-1 whitespace-pre-wrap text-slate-500">{source.excerpt}</p>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </article>
        ))}
        {isSending ? (
          <article className="flex justify-start">
            <div className="max-w-[85%] rounded-3xl rounded-bl-md bg-coral/10 px-4 py-3 text-sm leading-6 text-slate-700">
              <p>응답을 생성하는 중입니다...</p>
              <p className="mt-2 text-[11px] text-slate-400">잠시만 기다려주세요</p>
            </div>
          </article>
        ) : null}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-coral/15 bg-white px-4 py-4">
        <label htmlFor="chatbot-message" className="sr-only">
          챗봇 메시지 입력
        </label>
        <div className="rounded-[1.5rem] border border-coral/15 bg-sand p-2">
          <textarea
            id="chatbot-message"
            ref={inputRef}
            rows="3"
            value={draftMessage}
            onChange={(event) => setDraftMessage(event.target.value)}
            placeholder="등기부등본이나 계약 전 체크포인트에 대해 질문해보세요."
            className="w-full resize-none bg-transparent px-3 py-2 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400"
          />
          <div className="flex items-center justify-between px-2 pb-1 pt-2">
            <p className="text-xs text-slate-400">
              {error
                ? '일시적인 오류가 있었습니다. 다시 시도할 수 있습니다.'
                : '같은 탭 안에서는 페이지를 이동해도 대화가 유지됩니다.'}
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
