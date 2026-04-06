import { Outlet } from 'react-router-dom';
import FloatingChatbot from '../ui/FloatingChatbot';
import SiteHeader from '../ui/SiteHeader';

function AppShell() {
  return (
    <div className="min-h-screen bg-cream text-ink">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,_rgba(233,115,82,0.18),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(145,160,139,0.18),_transparent_28%)]" />
      <SiteHeader />
      <Outlet />
      <FloatingChatbot />
    </div>
  );
}

export default AppShell;
