import { Link, NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const navigationItems = [
  { label: '메인', to: '/' },
  { label: '새 분석', to: '/analysis/new' },
  { label: '매물 점검', to: '/listing-check' },
  { label: '챗봇', to: '/chatbot' },
  // 기록은 로그인해야 내용이 있다.
  { label: '분석 기록', to: '/history', authOnly: true },
];

function AuthMenu() {
  const { user, loading, logout } = useAuth();

  if (loading) {
    return null;
  }

  if (!user) {
    return (
      <Link
        to="/login"
        className="rounded-full border border-white/80 bg-white/70 px-4 py-2 text-sm font-medium text-slate-600 shadow-sm backdrop-blur transition hover:bg-coral/10 hover:text-ink"
      >
        로그인
      </Link>
    );
  }

  return (
    <div className="flex items-center gap-2 rounded-full border border-white/80 bg-white/70 px-4 py-2 shadow-sm backdrop-blur">
      <span className="text-sm font-medium text-ink">{user.name}님</span>
      <span className="text-slate-300">·</span>
      <button
        type="button"
        onClick={logout}
        className="text-sm text-slate-600 transition hover:text-coral"
      >
        로그아웃
      </button>
    </div>
  );
}

function SiteHeader() {
  const { user } = useAuth();
  const items = navigationItems.filter((item) => !item.authOnly || user);

  return (
    <header className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-6 lg:px-10">
      <Link to="/" className="text-sm font-semibold tracking-[0.24em] text-coral uppercase">
        Jeonse Risk AI
      </Link>
      <div className="flex items-center gap-3">
        <nav className="flex gap-3 rounded-full border border-white/80 bg-white/70 p-2 shadow-sm backdrop-blur">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `rounded-full px-4 py-2 text-sm font-medium transition ${
                  isActive ? 'bg-ink text-white' : 'text-slate-600 hover:bg-coral/10 hover:text-ink'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <AuthMenu />
      </div>
    </header>
  );
}

export default SiteHeader;
