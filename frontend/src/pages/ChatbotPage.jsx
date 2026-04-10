import ChatbotPanel from '../ui/ChatbotPanel';

function ChatbotPage() {
  return (
    <main className="mx-auto flex min-h-[calc(100vh-72px)] w-full max-w-6xl flex-col px-4 pb-8 pt-6 sm:px-6">
      <h1 className="mb-4 text-2xl font-semibold text-ink sm:text-3xl">전세 리스크 챗봇</h1>
      <p className="mb-6 text-sm text-slate-600">
        더 넓은 화면에서 질문하고, 이전 대화 맥락을 이어서 답변을 받을 수 있습니다.
      </p>
      <div className="flex-1">
        <ChatbotPanel className="h-[calc(100vh-220px)] min-h-[32rem]" />
      </div>
    </main>
  );
}

export default ChatbotPage;
