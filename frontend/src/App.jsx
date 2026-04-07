import { Navigate, Route, Routes } from 'react-router-dom';
import { ChatbotProvider } from './context/ChatbotContext';
import AppShell from './layout/AppShell';
import AnalysisNewPage from './pages/AnalysisNewPage';
import ChatbotPage from './pages/ChatbotPage';
import HomePage from './pages/HomePage';
import MapPage from './pages/MapPage';

function App() {
  return (
    <ChatbotProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/analysis/new" element={<AnalysisNewPage />} />
          <Route path="/chatbot" element={<ChatbotPage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </ChatbotProvider>
  );
}

export default App;
