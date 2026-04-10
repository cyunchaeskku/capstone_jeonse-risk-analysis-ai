import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatbot } from '../context/ChatbotContext';
import ChatbotPanel from './ChatbotPanel';

function FloatingChatbot() {
  const { closeChat, isOpen, toggleChat } = useChatbot();
  const navigate = useNavigate();

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

  const handleFullscreen = () => {
    navigate('/chatbot');
    closeChat();
  };

  return (
    <>
      <div className="fixed bottom-5 right-5 z-50 sm:bottom-7 sm:right-7">
        <button
          type="button"
          aria-label={isOpen ? '챗봇 닫기' : '챗봇 열기'}
          onClick={toggleChat}
          className="group flex h-16 w-16 items-center justify-center rounded-full bg-ink text-white shadow-[0_18px_40px_rgba(18,70,51,0.28)] transition hover:-translate-y-0.5 hover:bg-[#0f523d]"
        >
          <span className="text-xl font-semibold">{isOpen ? '×' : 'AI'}</span>
        </button>
      </div>

      {isOpen ? (
        <ChatbotPanel
          className="fixed inset-x-4 bottom-24 top-4 z-40 w-auto sm:inset-x-auto sm:bottom-28 sm:right-7 sm:top-6 sm:w-[24rem] md:w-[26rem]"
          onRequestClose={closeChat}
          onRequestFullscreen={handleFullscreen}
          showCloseButton
          showFullscreenButton
        />
      ) : null}
    </>
  );
}

export default FloatingChatbot;
