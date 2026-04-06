import { useEffect, useRef } from 'react';
import { useChatbot } from '../context/ChatbotContext';

function FloatingChatbot() {
  const {
    closeChat,
    draftMessage,
    error,
    isOpen,
    isSending,
    messages,
    sendMessage,
    setDraftMessage,
    toggleChat,
  } = useChatbot();
  const inputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        closeChat();
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [closeChat, isOpen]);

  const handleSubmit = (event) => {
    event.preventDefault();
    sendMessage();
  };

  return (
    <>
      <div className="fixed bottom-5 right-5 z-50 sm:bottom-7 sm:right-7">
        <button
          type="button"
          aria-label={isOpen ? '챗봇 닫기' : '챗봇 열기'}
          onClick={toggleChat}
          className="group flex h-16 w-16 items-center justify-center rounded-full bg-ink text-white shadow-[0_18px_40px_rgba(31,41,55,0.28)] transition hover:-translate-y-0.5 hover:bg-slate-800"
        >
          <span className="text-xl font-semibold">{isOpen ? '×' : 'AI'}</span>
        </button>
      </div>

      {isOpen ? (
        <section className="fixed inset-x-4 bottom-24 top-4 z-40 flex w-auto flex-col overflow-hidden rounded-[1.75rem] border border-white/80 bg-white/95 shadow-[0_28px_80px_rgba(31,41,55,0.18)] backdrop-blur sm:inset-x-auto sm:right-7 sm:top-6 sm:w-[24rem] sm:bottom-28 md:w-[26rem]">
          <header className="flex items-center justify-between border-b border-slate-200 bg-sand px-5 py-4">
            <div>
              <p className="text-sm font-semibold tracking-[0.18em] text-coral uppercase">Legal Assistant</p>
              <h2 className="mt-1 text-lg font-semibold text-slate-900">전세 리스크 챗봇</h2>
            </div>
            <button
              type="button"
              aria-label="챗봇 닫기"
              onClick={closeChat}
              className="rounded-full border border-slate-300 px-3 py-1 text-sm font-medium text-slate-600 transition hover:border-slate-400 hover:text-slate-900"
            >
              닫기
            </button>
          </header>

          <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
            {messages.map((message) => (
              <article
                key={message.id}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] rounded-3xl px-4 py-3 text-sm leading-6 ${
                    message.role === 'user'
                      ? 'rounded-br-md bg-ink text-white'
                      : message.isError
                        ? 'rounded-bl-md bg-red-50 text-red-700'
                        : 'rounded-bl-md bg-slate-100 text-slate-700'
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
                </div>
              </article>
            ))}
            {isSending ? (
              <article className="flex justify-start">
                <div className="max-w-[85%] rounded-3xl rounded-bl-md bg-slate-100 px-4 py-3 text-sm leading-6 text-slate-700">
                  <p>응답을 생성하는 중입니다...</p>
                  <p className="mt-2 text-[11px] text-slate-400">잠시만 기다려주세요</p>
                </div>
              </article>
            ) : null}
          </div>

          <form onSubmit={handleSubmit} className="border-t border-slate-200 bg-white px-4 py-4">
            <label htmlFor="chatbot-message" className="sr-only">
              챗봇 메시지 입력
            </label>
            <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-2">
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
                  className="rounded-full bg-coral px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#d96545] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSending ? '전송 중...' : '전송'}
                </button>
              </div>
            </div>
          </form>
        </section>
      ) : null}
    </>
  );
}

export default FloatingChatbot;
