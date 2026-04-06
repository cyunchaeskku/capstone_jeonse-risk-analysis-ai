import { createContext, useContext, useMemo, useState } from 'react';

const ChatbotContext = createContext(null);
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';
const HISTORY_TURN_LIMIT = 2;

const initialMessages = [
  {
    id: 'welcome',
    role: 'assistant',
    text: '안녕하세요. 전세계약 관련 위험 요소나 확인 포인트를 물어보면 구조적으로 정리해드릴게요.',
    timestamp: '지금',
  },
];

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
    timestamp: '방금 전',
    isError: options.isError ?? false,
  };
}

export function ChatbotProvider({ children }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState(initialMessages);
  const [draftMessage, setDraftMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState(null);

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
      timestamp: '방금 전',
    };
    const history = toRecentHistory(messages);

    setDraftMessage('');
    setIsOpen(true);
    setError(null);
    setIsSending(true);
    setMessages((current) => [...current, userMessage]);

    try {
      const response = await fetch(`${API_BASE_URL}/qa`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: trimmed,
          history,
        }),
      });

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const errorMessage = errorPayload?.detail?.message ?? `Request failed with status ${response.status}`;
        throw new Error(errorMessage);
      }

      const data = await response.json();
      setMessages((current) => [...current, buildAssistantMessage(data.answer)]);
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

  const value = useMemo(
    () => ({
      closeChat,
      draftMessage,
      error,
      isOpen,
      isSending,
      messages,
      openChat,
      sendMessage,
      setDraftMessage,
      toggleChat,
    }),
    [draftMessage, error, isOpen, isSending, messages],
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
