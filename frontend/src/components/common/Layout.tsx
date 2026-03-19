import { useEffect, useRef, useState, useCallback } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import { useStore } from '../../store';
import ClubBadge from './ClubBadge';
import { LeagueLogo } from '../LeagueLogo';
import {
  Home, Users, Crosshair, Swords, Dumbbell, ArrowRightLeft,
  BarChart3, Trophy, Newspaper, Calendar, AlertCircle,
  Play, Pause, FastForward, SkipForward,
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

type AdvanceSpeed = 'paused' | 'normal' | 'fast' | 'instant';

const SPEED_DELAYS: Record<Exclude<AdvanceSpeed, 'paused'>, number> = {
  normal: 2000,
  fast: 800,
  instant: 100,
};

export default function Layout() {
  const { club, seasonState, loading, error, advanceMatchday, fetchClub, fetchSeasonState } = useStore();

  const [speed, setSpeed] = useState<AdvanceSpeed>('paused');
  const [advanceCount, setAdvanceCount] = useState(0);
  const speedRef = useRef(speed);
  const loadingRef = useRef(loading);

  useEffect(() => { speedRef.current = speed; }, [speed]);
  useEffect(() => { loadingRef.current = loading; }, [loading]);

  const handleAdvance = useCallback(async () => {
    await advanceMatchday();
    await fetchClub();
    await fetchSeasonState();
    setAdvanceCount(c => c + 1);
  }, [advanceMatchday, fetchClub, fetchSeasonState]);

  useEffect(() => {
    if (speed === 'paused') return;

    let cancelled = false;

    const loop = async () => {
      while (!cancelled && speedRef.current !== 'paused') {
        if (loadingRef.current) {
          await new Promise(r => setTimeout(r, 200));
          continue;
        }

        await handleAdvance();

        const st = useStore.getState().seasonState;
        if (st && st.current_matchday >= st.total_matchdays) {
          setSpeed('paused');
          break;
        }

        const delay = SPEED_DELAYS[speedRef.current as Exclude<AdvanceSpeed, 'paused'>] ?? 2000;
        await new Promise(r => setTimeout(r, delay));
      }
    };

    loop();
    return () => { cancelled = true; };
  }, [speed, handleAdvance]);

  useEffect(() => {
    if (!club) fetchClub();
    if (!seasonState) fetchSeasonState();
  }, []);

  const cycleSpeed = () => {
    setSpeed(s => {
      if (s === 'paused') return 'normal';
      if (s === 'normal') return 'fast';
      if (s === 'fast') return 'instant';
      return 'paused';
    });
  };

  const SpeedIcon = speed === 'paused' ? Play
    : speed === 'normal' ? FastForward
      : speed === 'fast' ? SkipForward
        : SkipForward;

  const speedLabel = speed === 'paused' ? 'Advance Day'
    : speed === 'normal' ? 'Auto: Normal'
      : speed === 'fast' ? 'Auto: Fast'
        : 'Auto: Instant';

  const isSeasonOver = seasonState && seasonState.current_matchday >= seasonState.total_matchdays;

  return (
    <div className="flex h-screen overflow-hidden">
      <nav className="w-64 flex-shrink-0 bg-[var(--fm-surface)] border-r border-[var(--fm-border)] flex flex-col shadow-xl z-20">
        <div className="p-4 border-b border-[var(--fm-border)]">
          <div className="flex items-center gap-3 mb-2">
            <ClubBadge
              clubId={club?.id}
              name={club?.name ?? 'FM'}
              primaryColor={club?.primary_color}
              size={40}
            />
            <div className="min-w-0">
              <h1 className="text-sm font-bold text-[var(--fm-text)] truncate leading-tight">
                {club?.name ?? 'Football Manager'}
              </h1>
              {club?.league_name && (
                <div className="flex items-center gap-1.5 mt-1">
                  <LeagueLogo
                    leagueId={club.league_name === 'Premier League' ? 1 : club.league_name === 'La Liga' ? 7 : club.league_name === 'Bundesliga' ? 12 : club.league_name === 'Serie A' ? 15 : club.league_name === 'Ligue 1' ? 20 : 1}
                    leagueName={club.league_name}
                    size={12}
                  />
                  <span className="text-[10px] text-[var(--fm-text-muted)] truncate">{club.league_name}</span>
                </div>
              )}
            </div>
          </div>
          {seasonState && (
            <div className="flex items-center gap-2 mt-3 px-2 py-1 rounded-md bg-[var(--fm-surface2)] text-[10px] text-[var(--fm-text-muted)] w-fit">
              <Calendar size={10} />
              <span>S{seasonState.season} &middot; MD {seasonState.current_matchday}/{seasonState.total_matchdays}</span>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto py-2 custom-scrollbar">
          {navGroups.map((group, gi) => (
            <div key={group.label} className="mb-4">
              <p className="px-5 pt-2 pb-1 text-[10px] uppercase tracking-widest text-[var(--fm-text-muted)] font-black opacity-50">
                {group.label}
              </p>
              {group.items.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-5 py-2.5 text-[13px] relative transition-all group ${isActive
                      ? 'text-[var(--fm-accent)] bg-[var(--fm-accent)]/8 font-semibold'
                      : 'text-[var(--fm-text-muted)] hover:text-[var(--fm-text)] hover:bg-[var(--fm-surface2)]'
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <div className="absolute left-0 top-1 bottom-1 w-[3px] rounded-r bg-[var(--fm-accent)] shadow-[0_0_8px_var(--fm-accent)]" />
                      )}
                      <Icon size={18} strokeWidth={isActive ? 2.5 : 1.5} className={isActive ? 'text-[var(--fm-accent)]' : 'group-hover:scale-110 transition-transform'} />
                      <span>{label}</span>
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </div>

        <div className="p-4 border-t border-[var(--fm-border)] bg-[var(--fm-surface)]/50 backdrop-blur-sm space-y-3">
          {speed !== 'paused' && (
            <div className="flex items-center justify-between text-[10px] text-[var(--fm-text-muted)] px-1">
              <span className="flex items-center gap-1.5 font-medium">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-[var(--fm-green)] animate-pulse" />
                Simulating
              </span>
              <span className="tabular-nums font-bold text-[var(--fm-text)]">{advanceCount} days</span>
            </div>
          )}

          <div className="flex gap-2">
            <button
              onClick={speed === 'paused' ? handleAdvance : cycleSpeed}
              disabled={(loading && speed === 'paused') || !!isSeasonOver}
              className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-bold
                shadow-lg transition-all active:scale-95
                ${speed !== 'paused'
                  ? 'bg-[var(--fm-green)] text-white shadow-green-500/20 hover:brightness-110'
                  : 'bg-[var(--fm-accent)] text-white shadow-blue-500/15 hover:brightness-110'
                }
                disabled:opacity-40 disabled:cursor-not-allowed`}
            >
              {loading && speed === 'paused' ? (
                <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <SpeedIcon size={18} />
              )}
              {loading && speed === 'paused' ? 'Processing...' : isSeasonOver ? 'Season Over' : speedLabel}
            </button>

            {speed !== 'paused' && (
              <button
                onClick={() => { setSpeed('paused'); setAdvanceCount(0); }}
                className="w-12 flex items-center justify-center rounded-xl
                  bg-[var(--fm-red)]/10 text-[var(--fm-red)] border border-[var(--fm-red)]/20
                  hover:bg-[var(--fm-red)] hover:text-white transition-all shadow-lg shadow-red-500/10 active:scale-95"
                title="Stop auto-advance"
              >
                <Pause size={18} />
              </button>
            )}
          </div>
        </div>
      </nav>

      <main className="flex-1 overflow-y-auto bg-[var(--fm-bg)] relative">
        <div className="fixed top-0 left-64 right-0 h-32 bg-gradient-to-b from-[var(--fm-bg)] to-transparent pointer-events-none z-10" />

        {error && (
          <div className="mx-8 mt-6 p-4 rounded-xl bg-[var(--fm-red)]/5 border border-[var(--fm-red)]/20 flex items-center gap-3 text-sm text-[var(--fm-red)] shadow-sm backdrop-blur-md">
            <AlertCircle size={18} />
            <div className="flex-1">
              <p className="font-semibold">{error}</p>
              <p className="text-[11px] opacity-70 mt-0.5">Please ensure the backend API server is running (uv run python -m fm --api)</p>
            </div>
          </div>
        )}

        <div className="p-8 max-w-[1500px] mx-auto min-h-full">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
