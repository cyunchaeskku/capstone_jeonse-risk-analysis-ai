import { createContext, useContext, useEffect, useMemo, useState } from 'react';

const ChatbotContext = createContext(null);
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';
const HISTORY_TURN_LIMIT = 2;
const STORAGE_KEY = 'jeonse_chat_v1';
// sources에 법령 원문이 들어가 대화가 길어지면 용량이 커진다. 최근 것만 남긴다.
const STORED_MESSAGE_LIMIT = 50;
const timestampFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Seoul',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

function formatTimestamp(date = new Date()) {
  return timestampFormatter.format(date);
}

const initialMessages = [
  {
    id: 'welcome',
    role: 'assistant',
    text: '안녕하세요. 전세계약 관련 위험 요소나 확인 포인트를 물어보면 구조적으로 정리해드릴게요.',
    timestamp: formatTimestamp(),
  },
];

// 새로고침으로 대화가 통째로 날아가지 않게 한다. 이 단말에만 남고 서버와는 무관하다.
function loadStoredChat() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return parsed?.messages?.length ? parsed : null;
  } catch {
    // 시크릿 모드나 사이트 데이터 차단
    return null;
  }
}

function toRecentHistory(messages) {
  const conversationalMessages = messages.filter(
    (message) =>
      (message.role === 'user' || message.role === 'assistant') &&
      message.id !== 'welcome' &&
      !message.isError,
  );
  return conversationalMessages.slice(-(HISTORY_TURN_LIMIT * 2)).map((message) => ({
    role: message.role,
    text: message.text,
  }));
}

function buildAssistantMessage(text, options = {}) {
  return {
    id: options.id ?? `assistant-${Date.now()}`,
    role: 'assistant',
    text,
    timestamp: formatTimestamp(),
    isError: options.isError ?? false,
    references: options.references ?? [],
    sources: options.sources ?? [],
  };
}

function parseSseEvent(rawEvent) {
  const lines = rawEvent.split('\n');
  const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim() ?? 'message';
  const data = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n');

  return { event, data: JSON.parse(data) };
}

export function ChatbotProvider({ children }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState(() => loadStoredChat()?.messages ?? initialMessages);
  const [draftMessage, setDraftMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState(null);
  // 어느 분석에 대한 질문인지는 사용자가 직접 고른다. 최근 기록을 자동으로
  // 붙이면 다른 매물을 근거로 답할 수 있다. { analysisId, listingName }
  const [activeAnalysis, setActiveAnalysis] = useState(() => loadStoredChat()?.activeAnalysis ?? null);

  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ messages: messages.slice(-STORED_MESSAGE_LIMIT), activeAnalysis }),
      );
    } catch {
      // 용량 초과나 저장 차단. 저장 실패가 대화를 막을 이유는 없다.
    }
  }, [messages, activeAnalysis]);

  const openChat = () => setIsOpen(true);
  const closeChat = () => setIsOpen(false);
  const toggleChat = () => setIsOpen((current) => !current);

  const sendMessage = async () => {
    const trimmed = draftMessage.trim();

    if (!trimmed || isSending) {
      return;
    }

    const userMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      text: trimmed,
      timestamp: formatTimestamp(),
    };
    const history = toRecentHistory(messages);

    setDraftMessage('');
    setIsOpen(true);
    setError(null);
    setIsSending(true);
    setMessages((current) => [...current, userMessage]);

    try {
      const assistantMessageId = `assistant-${Date.now()}`;
      const response = await fetch(`${API_BASE_URL}/qa`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: trimmed,
          history,
          analysis_id: activeAnalysis?.analysisId ?? null,
        }),
      });

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const errorMessage = errorPayload?.detail?.message ?? `Request failed with status ${response.status}`;
        throw new Error(errorMessage);
      }

      if (!response.body) {
        throw new Error('스트리밍 응답을 읽을 수 없습니다.');
      }

      setMessages((current) => [...current, buildAssistantMessage('', { id: assistantMessageId })]);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let answer = '';
      let buffer = '';
      let completed = false;

      while (!completed) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });

        const events = buffer.split('\n\n');
        buffer = events.pop() ?? '';

        for (const rawEvent of events) {
          if (!rawEvent.trim()) {
            continue;
          }

          const { event, data } = parseSseEvent(rawEvent);
          if (event === 'token') {
            answer += data.text;
            setMessages((current) =>
              current.map((message) => (message.id === assistantMessageId ? { ...message, text: answer } : message)),
            );
          }

          if (event === 'done') {
            completed = true;
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantMessageId
                  ? { ...message, references: data.references ?? [], sources: data.sources ?? [] }
                  : message,
              ),
            );
          }

          if (event === 'error') {
            throw new Error(data.message ?? '챗봇 응답을 가져오지 못했습니다.');
          }
        }

        if (done && !completed) {
          throw new Error('챗봇 스트리밍 응답이 중단되었습니다.');
        }
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unknown error');
      setMessages((current) => [
        ...current,
        buildAssistantMessage('챗봇 응답을 가져오지 못했습니다. 잠시 후 다시 시도해주세요.', {
          id: `assistant-error-${Date.now()}`,
          isError: true,
        }),
      ]);
    } finally {
      setIsSending(false);
    }
  };

  // 새로고침이 더 이상 대화를 비우지 않으므로 초기화 수단이 필요하다.
  const resetChat = () => {
    setMessages(initialMessages);
    setActiveAnalysis(null);
    setError(null);
  };

  const askAboutAnalysis = (analysisId, listingName) => {
    setActiveAnalysis({ analysisId, listingName });
    setIsOpen(true);
  };

  const value = useMemo(
    () => ({
      activeAnalysis,
      askAboutAnalysis,
      clearActiveAnalysis: () => setActiveAnalysis(null),
      closeChat,
      draftMessage,
      error,
      isOpen,
      isSending,
      messages,
      openChat,
      resetChat,
      sendMessage,
      setDraftMessage,
      toggleChat,
    }),
    [activeAnalysis, draftMessage, error, isOpen, isSending, messages],
  );

  return <ChatbotContext.Provider value={value}>{children}</ChatbotContext.Provider>;
}

export function useChatbot() {
  const context = useContext(ChatbotContext);

  if (!context) {
    throw new Error('useChatbot must be used within a ChatbotProvider');
  }

  return context;
}
