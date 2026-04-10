import { Link, NavLink } from 'react-router-dom';

const navigationItems = [
  { label: '메인', to: '/' },
  { label: '새 분석', to: '/analysis/new' },
  { label: '지도', to: '/map' },
];

function SiteHeader() {
  return (
    <header className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-6 lg:px-10">
      <Link to="/" className="text-sm font-semibold tracking-[0.24em] text-coral uppercase">
        Jeonse Risk AI
      </Link>
      <nav className="flex gap-3 rounded-full border border-white/80 bg-white/70 p-2 shadow-sm backdrop-blur">
        {navigationItems.map((item) => (
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
    </header>
  );
}

export default SiteHeader;
