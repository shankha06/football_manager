import { useEffect } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useStore } from '../../store';
import {
  Home, Users, Crosshair, Swords, Dumbbell, ArrowRightLeft,
  BarChart3, Trophy, Newspaper, ChevronRight, Calendar, Shield, AlertCircle,
} from 'lucide-react';

const navGroups = [
  {
    label: 'Game',
    items: [
      { to: '/dashboard', icon: Home, label: 'Dashboard' },
      { to: '/match', icon: Swords, label: 'Match Day' },
      { to: '/news', icon: Newspaper, label: 'News' },
    ],
  },
  {
    label: 'Squad',
    items: [
      { to: '/squad', icon: Users, label: 'Squad' },
      { to: '/tactics', icon: Crosshair, label: 'Tactics' },
      { to: '/training', icon: Dumbbell, label: 'Training' },
      { to: '/transfers', icon: ArrowRightLeft, label: 'Transfers' },
    ],
  },
  {
    label: 'Data',
    items: [
      { to: '/table', icon: Trophy, label: 'League Table' },
      { to: '/analytics', icon: BarChart3, label: 'Analytics' },
    ],
  },
];

export default function Layout() {
  const { club, seasonState, loading, error, advanceMatchday, fetchClub, fetchSeasonState } = useStore();
  const navigate = useNavigate();

  const handleAdvance = async () => {
    await advanceMatchday();
    await fetchClub();
    await fetchSeasonState();
  };

  // Fetch on mount if not already loaded
  useEffect(() => {
    if (!club) fetchClub();
    if (!seasonState) fetchSeasonState();
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <nav className="w-56 flex-shrink-0 bg-[var(--fm-surface)] border-r border-[var(--fm-border)] flex flex-col">
        {/* Club header */}
        <div className="p-4 border-b border-[var(--fm-border)]">
          <div className="flex items-center gap-2.5 mb-2">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ backgroundColor: club?.primary_color || 'var(--fm-accent)' }}
            >
              <Shield size={14} className="text-white" />
            </div>
            <div className="min-w-0">
              <h1 className="text-sm font-bold text-[var(--fm-text)] truncate leading-tight">
                {club?.name ?? 'Football Manager'}
              </h1>
              {seasonState && (
                <div className="flex items-center gap-1 text-[10px] text-[var(--fm-text-muted)] leading-tight mt-0.5">
                  <Calendar size={9} />
                  <span>S{seasonState.season}</span>
                  <span className="text-[var(--fm-border)]">|</span>
                  <span>MD {seasonState.current_matchday}/{seasonState.total_matchdays}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Nav items */}
        <div className="flex-1 overflow-y-auto py-2">
          {navGroups.map((group, gi) => (
            <div key={group.label}>
              {gi > 0 && (
                <div className="mx-4 my-2 border-t border-[var(--fm-border)]" />
              )}
              <p className="px-4 pt-2 pb-1 text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)] font-semibold">
                {group.label}
              </p>
              {group.items.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 px-4 py-2 text-[13px] relative transition-all ${
                      isActive
                        ? 'text-[var(--fm-accent)] bg-[var(--fm-accent)]/8'
                        : 'text-[var(--fm-text-muted)] hover:text-[var(--fm-text)] hover:bg-[var(--fm-surface2)]'
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <div className="absolute left-0 top-1 bottom-1 w-[3px] rounded-r bg-[var(--fm-accent)]" />
                      )}
                      <Icon size={16} strokeWidth={isActive ? 2.2 : 1.8} />
                      <span className={isActive ? 'font-medium' : ''}>{label}</span>
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </div>

        {/* Bottom advance button */}
        <div className="p-3 border-t border-[var(--fm-border)]">
          <button
            onClick={handleAdvance}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold
              bg-[var(--fm-accent)] text-white hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed
              shadow-lg shadow-blue-500/15"
          >
            {loading ? (
              <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <ChevronRight size={16} />
            )}
            {loading ? 'Processing...' : 'Advance Day'}
          </button>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        {error && (
          <div className="mx-6 mt-4 p-3 rounded-lg bg-[var(--fm-red)]/10 border border-[var(--fm-red)]/30 flex items-center gap-2 text-sm text-[var(--fm-red)]">
            <AlertCircle size={16} />
            <span>{error}</span>
            <span className="text-xs text-[var(--fm-text-muted)] ml-auto">Is the API server running? (uv run python -m fm --api)</span>
          </div>
        )}
        <div className="p-6 max-w-[1400px] mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
