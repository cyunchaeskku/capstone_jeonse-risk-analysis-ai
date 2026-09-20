import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ChatbotProvider } from './context/ChatbotContext';
import AppShell from './layout/AppShell';
import AnalysisNewPage from './pages/AnalysisNewPage';
import ChatbotPage from './pages/ChatbotPage';
import HomePage from './pages/HomePage';
import ListingCheckPage from './pages/ListingCheckPage';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';

function App() {
  return (
    <AuthProvider>
      <ChatbotProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/analysis/new" element={<AnalysisNewPage />} />
            <Route path="/chatbot" element={<ChatbotPage />} />
            <Route path="/listing-check" element={<ListingCheckPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </ChatbotProvider>
    </AuthProvider>
  );
}

export default App;
