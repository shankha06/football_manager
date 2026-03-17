import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import { motion } from 'framer-motion';
import {
  Calendar, TrendingUp, DollarSign, Heart, Newspaper, Trophy,
  Swords, ShieldAlert, Users, Activity, ChevronRight,
  Lock, Unlock, ArrowRightLeft,
} from 'lucide-react';

const fadeUp = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.35, ease: 'easeOut' },
};

export default function Dashboard() {
  const {
    club, board, seasonState, standings, news, players,
    fetchClub, fetchBoard, fetchSeasonState, fetchStandings, fetchNews, fetchSquad,
  } = useStore();
  const navigate = useNavigate();

  useEffect(() => {
    fetchClub();
    fetchBoard();
    fetchSeasonState();
    fetchStandings();
    fetchNews();
    fetchSquad();
  }, []);

  const ourStanding = standings.find(s => s.club_id === club?.id);
  const position = ourStanding ? standings
    .sort((a, b) => b.points - a.points || b.goal_difference - a.goal_difference || b.goals_for - a.goals_for)
    .indexOf(ourStanding) + 1 : null;

  const injuredPlayers = players.filter(p => p.injured_weeks > 0);
  const suspendedPlayers = players.filter(p => p.suspended_matches > 0);
  const lowMoralePlayers = players.filter(p => p.morale < 40 && p.injured_weeks === 0);

  const wagePercent = club ? Math.min(100, (club.total_wages / club.wage_budget) * 100) : 0;
  const teamSpirit = club?.team_spirit ?? 0;

  const avgOvr = players.length > 0
    ? (players.reduce((s, p) => s + p.overall, 0) / players.length).toFixed(1)
    : '--';
  const avgAge = players.length > 0
    ? (players.reduce((s, p) => s + p.age, 0) / players.length).toFixed(1)
    : '--';

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{club?.name ?? 'Loading...'}</h1>
          <p className="text-sm text-[var(--fm-text-muted)]">
            {club?.league_name}
            {seasonState && <> &middot; Season {seasonState.season}, Matchday {seasonState.current_matchday}</>}
          </p>
        </div>
        <button
          onClick={() => navigate('/match')}
          className="px-5 py-2.5 bg-[var(--fm-accent)] text-white rounded-lg font-semibold text-sm
            hover:brightness-110 flex items-center gap-2 shadow-lg shadow-blue-500/20"
        >
          <Swords size={16} /> Play Next Match
        </button>
      </div>

      {/* 3-column grid */}
      <div className="grid grid-cols-12 gap-4">

        {/* -- LEFT COLUMN (5 cols) -- */}
        <div className="col-span-5 space-y-4">

          {/* Next Match */}
          <motion.div {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.05 }}>
            <div
              className="card card-interactive"
              onClick={() => navigate('/match')}
            >
              <div className="flex items-center gap-2 mb-3">
                <Calendar size={14} className="text-[var(--fm-accent)]" />
                <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)]">
                  Next Match
                </span>
                <span className="ml-auto text-[10px] text-[var(--fm-text-muted)] bg-[var(--fm-surface2)] px-2 py-0.5 rounded">
                  Matchday {(seasonState?.current_matchday ?? 0) + 1}
                </span>
              </div>
              <div className="flex items-center justify-between py-3">
                <div className="flex items-center gap-3">
                  <div
                    className="w-12 h-12 rounded-lg flex items-center justify-center text-white font-bold text-sm shadow-lg"
                    style={{ backgroundColor: club?.primary_color || 'var(--fm-accent)' }}
                  >
                    {club?.short_name?.slice(0, 3) ?? club?.name?.slice(0, 3) ?? '---'}
                  </div>
                  <div>
                    <p className="font-semibold text-sm">{club?.name ?? '---'}</p>
                    <p className="text-[10px] text-[var(--fm-text-muted)]">Home</p>
                  </div>
                </div>
                <div className="text-center px-4">
                  <div className="w-10 h-10 rounded-full bg-[var(--fm-surface2)] flex items-center justify-center">
                    <span className="text-sm font-bold text-[var(--fm-text-muted)]">vs</span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <p className="font-semibold text-sm text-[var(--fm-text-muted)]">Opponent</p>
                    <p className="text-[10px] text-[var(--fm-text-muted)]">Away</p>
                  </div>
                  <div className="w-12 h-12 rounded-lg bg-[var(--fm-surface2)] flex items-center justify-center shadow-lg">
                    <Swords size={18} className="text-[var(--fm-text-muted)]" />
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-center mt-1 pt-2 border-t border-[var(--fm-border)]">
                <span className="text-xs text-[var(--fm-accent)] font-medium flex items-center gap-1">
                  Click to view fixture details <ChevronRight size={12} />
                </span>
              </div>
            </div>
          </motion.div>

          {/* Recent Form */}
          <motion.div {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.1 }}>
            <div className="card">
              <div className="flex items-center gap-2 mb-3">
                <Activity size={14} className="text-[var(--fm-accent)]" />
                <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)]">
                  Recent Form
                </span>
              </div>
              {ourStanding?.form ? (
                <div className="flex gap-1.5">
                  {ourStanding.form.split('').map((r, i) => (
                    <div
                      key={i}
                      className={`w-9 h-9 flex items-center justify-center rounded-lg text-xs font-bold ${
                        r === 'W' ? 'bg-[var(--fm-green)]/15 text-[var(--fm-green)] border border-[var(--fm-green)]/25' :
                        r === 'D' ? 'bg-[var(--fm-yellow)]/15 text-[var(--fm-yellow)] border border-[var(--fm-yellow)]/25' :
                        'bg-[var(--fm-red)]/15 text-[var(--fm-red)] border border-[var(--fm-red)]/25'
                      }`}
                    >
                      {r}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-[var(--fm-text-muted)]">No matches played yet</p>
              )}
            </div>
          </motion.div>

          {/* Squad Overview */}
          <motion.div {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.15 }}>
            <div
              className="card card-interactive"
              onClick={() => navigate('/squad')}
            >
              <div className="flex items-center gap-2 mb-3">
                <Users size={14} className="text-[var(--fm-accent)]" />
                <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)]">
                  Squad Overview
                </span>
                <ChevronRight size={12} className="ml-auto text-[var(--fm-text-muted)]" />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div className="text-center p-2 rounded-lg bg-[var(--fm-surface2)]">
                  <p className="text-lg font-bold tabular-nums">{players.length}</p>
                  <p className="text-[10px] text-[var(--fm-text-muted)]">Players</p>
                </div>
                <div className="text-center p-2 rounded-lg bg-[var(--fm-surface2)]">
                  <p className="text-lg font-bold tabular-nums">{avgOvr}</p>
                  <p className="text-[10px] text-[var(--fm-text-muted)]">Avg OVR</p>
                </div>
                <div className="text-center p-2 rounded-lg bg-[var(--fm-surface2)]">
                  <p className="text-lg font-bold tabular-nums">{avgAge}</p>
                  <p className="text-[10px] text-[var(--fm-text-muted)]">Avg Age</p>
                </div>
              </div>
            </div>
          </motion.div>
        </div>

        {/* -- CENTER COLUMN (4 cols) -- */}
        <div className="col-span-4 space-y-4">

          {/* League Position */}
          <motion.div {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.08 }}>
            <div
              className="card card-interactive"
              onClick={() => navigate('/table')}
            >
              <div className="flex items-center gap-2 mb-2">
                <Trophy size={14} className="text-[var(--fm-yellow)]" />
                <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)]">
                  League Position
                </span>
                <ChevronRight size={12} className="ml-auto text-[var(--fm-text-muted)]" />
              </div>
              {ourStanding && position ? (
                <div className="flex items-end gap-4">
                  <div>
                    <span className="text-4xl font-black tabular-nums leading-none">
                      {position}
                    </span>
                    <span className="text-lg font-bold text-[var(--fm-text-muted)]">
                      {getOrdinal(position)}
                    </span>
                  </div>
                  <div className="flex-1 space-y-1.5 pb-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[var(--fm-text-muted)]">Points</span>
                      <span className="font-bold tabular-nums text-sm">{ourStanding.points}</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[var(--fm-text-muted)]">W-D-L</span>
                      <span className="tabular-nums">
                        <span className="text-[var(--fm-green)] font-semibold">{ourStanding.won}</span>
                        <span className="text-[var(--fm-text-muted)]">-</span>
                        <span className="text-[var(--fm-yellow)] font-semibold">{ourStanding.drawn}</span>
                        <span className="text-[var(--fm-text-muted)]">-</span>
                        <span className="text-[var(--fm-red)] font-semibold">{ourStanding.lost}</span>
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[var(--fm-text-muted)]">GD</span>
                      <span className={`font-bold tabular-nums ${ourStanding.goal_difference > 0 ? 'text-[var(--fm-green)]' : ourStanding.goal_difference < 0 ? 'text-[var(--fm-red)]' : ''}`}>
                        {ourStanding.goal_difference > 0 ? '+' : ''}{ourStanding.goal_difference}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[var(--fm-text-muted)]">GF/GA</span>
                      <span className="tabular-nums">{ourStanding.goals_for}/{ourStanding.goals_against}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-[var(--fm-text-muted)]">--</p>
              )}
            </div>
          </motion.div>

          {/* Squad Alerts */}
          <motion.div {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.12 }}>
            <div className="card">
              <div className="flex items-center gap-2 mb-3">
                <ShieldAlert size={14} className="text-[var(--fm-orange)]" />
                <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)]">
                  Squad Alerts
                </span>
                {(injuredPlayers.length + suspendedPlayers.length + lowMoralePlayers.length) > 0 && (
                  <span className="ml-auto text-[10px] font-bold bg-[var(--fm-red)]/15 text-[var(--fm-red)] px-2 py-0.5 rounded-full">
                    {injuredPlayers.length + suspendedPlayers.length + lowMoralePlayers.length}
                  </span>
                )}
              </div>
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {injuredPlayers.map(p => (
                  <div key={p.id} className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-[var(--fm-surface2)]">
                    <div className="w-1.5 h-1.5 rounded-full bg-[var(--fm-red)] flex-shrink-0" />
                    <span className="truncate flex-1">{p.name}</span>
                    <span className="text-[var(--fm-red)] font-semibold tabular-nums">{p.injured_weeks}w injured</span>
                  </div>
                ))}
                {suspendedPlayers.map(p => (
                  <div key={p.id} className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-[var(--fm-surface2)]">
                    <div className="w-1.5 h-1.5 rounded-full bg-[var(--fm-yellow)] flex-shrink-0" />
                    <span className="truncate flex-1">{p.name}</span>
                    <span className="text-[var(--fm-yellow)] font-semibold tabular-nums">{p.suspended_matches}m ban</span>
                  </div>
                ))}
                {lowMoralePlayers.map(p => (
                  <div key={p.id} className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-[var(--fm-surface2)]">
                    <div className="w-1.5 h-1.5 rounded-full bg-[var(--fm-orange)] flex-shrink-0" />
                    <span className="truncate flex-1">{p.name}</span>
                    <span className="text-[var(--fm-orange)] font-semibold tabular-nums">{p.morale.toFixed(0)}% morale</span>
                  </div>
                ))}
                {injuredPlayers.length === 0 && suspendedPlayers.length === 0 && lowMoralePlayers.length === 0 && (
                  <p className="text-xs text-[var(--fm-green)] py-1 px-2">All players available and fit</p>
                )}
              </div>
            </div>
          </motion.div>
        </div>

        {/* -- RIGHT COLUMN (3 cols) -- */}
        <div className="col-span-3 space-y-4">

          {/* Finances */}
          <motion.div {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.1 }}>
            <div className="card">
              <div className="flex items-center gap-2 mb-3">
                <DollarSign size={14} className="text-[var(--fm-green)]" />
                <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)]">
                  Finances
                </span>
              </div>
              <div className="space-y-3">
                <div>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-[var(--fm-text-muted)]">Transfer Budget</span>
                    <span className="font-bold tabular-nums">{formatMoney(club?.budget ?? 0)}</span>
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-[var(--fm-text-muted)]">Wages</span>
                    <span className="font-medium tabular-nums text-[10px]">
                      {formatMoney(club?.total_wages ?? 0)} / {formatMoney(club?.wage_budget ?? 0)}
                    </span>
                  </div>
                  <div className="h-2 bg-[var(--fm-surface2)] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full animate-fill"
                      style={{
                        width: `${wagePercent}%`,
                        backgroundColor: wagePercent > 90 ? 'var(--fm-red)' : wagePercent > 70 ? 'var(--fm-yellow)' : 'var(--fm-green)',
                      }}
                    />
                  </div>
                  <p className="text-[10px] text-[var(--fm-text-muted)] mt-1 tabular-nums">{wagePercent.toFixed(0)}% of budget</p>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Board Confidence */}
          <motion.div {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.14 }}>
            <div className="card">
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp size={14} className="text-[var(--fm-accent)]" />
                <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)]">
                  Board
                </span>
              </div>
              {board ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-center">
                    <div className="relative w-20 h-20">
                      <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                        <circle
                          cx="18" cy="18" r="15.5"
                          fill="none"
                          stroke="var(--fm-surface2)"
                          strokeWidth="2.5"
                        />
                        <circle
                          cx="18" cy="18" r="15.5"
                          fill="none"
                          stroke={board.board_confidence > 60 ? 'var(--fm-green)' : board.board_confidence > 30 ? 'var(--fm-yellow)' : 'var(--fm-red)'}
                          strokeWidth="2.5"
                          strokeDasharray={`${board.board_confidence * 0.974} 100`}
                          strokeLinecap="round"
                        />
                      </svg>
                      <div className="absolute inset-0 flex items-center justify-center">
                        <span className="text-base font-bold tabular-nums">{board.board_confidence.toFixed(0)}</span>
                      </div>
                    </div>
                  </div>
                  <div className="text-center space-y-1">
                    <p className="text-[10px] text-[var(--fm-text-muted)]">
                      Target: {board.min_league_position}-{board.max_league_position}
                    </p>
                    {board.ultimatum_active && (
                      <p className="text-[10px] text-[var(--fm-red)] font-bold uppercase tracking-wide">
                        Ultimatum Active
                      </p>
                    )}
                    {board.transfer_embargo && (
                      <p className="text-[10px] text-[var(--fm-red)] font-bold uppercase tracking-wide">
                        Transfer Embargo
                      </p>
                    )}
                  </div>
                </div>
              ) : (
                <p className="text-[var(--fm-text-muted)] text-sm">--</p>
              )}
            </div>
          </motion.div>

          {/* Team Spirit */}
          <motion.div {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.18 }}>
            <div className="card">
              <div className="flex items-center gap-2 mb-3">
                <Heart size={14} className="text-[var(--fm-red)]" />
                <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)]">
                  Team Spirit
                </span>
                <span className="ml-auto text-sm font-bold tabular-nums">
                  {teamSpirit.toFixed(0)}%
                </span>
              </div>
              <div className="h-2.5 bg-[var(--fm-surface2)] rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full animate-fill"
                  style={{
                    width: `${teamSpirit}%`,
                    backgroundColor: teamSpirit > 70 ? 'var(--fm-green)' : teamSpirit > 40 ? 'var(--fm-yellow)' : 'var(--fm-red)',
                  }}
                />
              </div>
              <p className="text-[10px] text-[var(--fm-text-muted)] mt-1.5 font-medium">
                {teamSpirit > 80 ? 'Superb' : teamSpirit > 60 ? 'Good' : teamSpirit > 40 ? 'Average' : teamSpirit > 20 ? 'Poor' : 'Very Poor'}
              </p>
            </div>
          </motion.div>

          {/* Transfer Window */}
          <motion.div {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.22 }}>
            <div className="card">
              <div className="flex items-center gap-2">
                <ArrowRightLeft size={14} className="text-[var(--fm-text-muted)]" />
                <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)]">
                  Transfer Window
                </span>
                <span className="ml-auto">
                  {seasonState && seasonState.phase === 'transfer' ? (
                    <span className="text-[10px] font-bold bg-[var(--fm-green)]/15 text-[var(--fm-green)] px-2 py-0.5 rounded-full flex items-center gap-1">
                      <Unlock size={9} /> Open
                    </span>
                  ) : (
                    <span className="text-[10px] font-bold bg-[var(--fm-surface2)] text-[var(--fm-text-muted)] px-2 py-0.5 rounded-full flex items-center gap-1">
                      <Lock size={9} /> Closed
                    </span>
                  )}
                </span>
              </div>
            </div>
          </motion.div>
        </div>

        {/* -- BOTTOM: NEWS -- */}
        <motion.div
          className="col-span-12"
          {...fadeUp}
          transition={{ ...fadeUp.transition, delay: 0.25 }}
        >
          <div className="card">
            <div className="flex items-center gap-2 mb-3">
              <Newspaper size={14} className="text-[var(--fm-accent)]" />
              <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)]">
                Latest News
              </span>
              <button
                onClick={() => navigate('/news')}
                className="ml-auto text-[10px] text-[var(--fm-accent)] hover:underline flex items-center gap-0.5"
              >
                View All <ChevronRight size={10} />
              </button>
            </div>
            <div className="grid grid-cols-5 gap-3">
              {news.slice(0, 5).map(n => (
                <div
                  key={n.id}
                  className={`p-3 rounded-lg border text-xs cursor-pointer hover:border-[var(--fm-accent)] transition-all ${
                    !n.is_read
                      ? 'border-[var(--fm-accent)]/30 bg-[var(--fm-accent)]/5 unread-glow'
                      : 'border-[var(--fm-border)] bg-[var(--fm-surface2)]'
                  }`}
                  onClick={() => navigate('/news')}
                >
                  <span className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase mb-1.5 ${getCategoryStyle(n.category)}`}>
                    {n.category}
                  </span>
                  <p className={`line-clamp-2 leading-snug ${!n.is_read ? 'text-[var(--fm-text)]' : 'text-[var(--fm-text-muted)]'}`}>
                    {n.headline}
                  </p>
                  {n.matchday && (
                    <p className="text-[9px] text-[var(--fm-text-muted)] mt-1.5">
                      MD {n.matchday}
                    </p>
                  )}
                </div>
              ))}
              {news.length === 0 && (
                <p className="col-span-5 text-xs text-[var(--fm-text-muted)] text-center py-4">No news yet</p>
              )}
            </div>
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}

function getCategoryStyle(category: string): string {
  switch (category) {
    case 'match': return 'bg-[var(--fm-accent)]/15 text-[var(--fm-accent)]';
    case 'transfer': return 'bg-[var(--fm-green)]/15 text-[var(--fm-green)]';
    case 'injury': return 'bg-[var(--fm-red)]/15 text-[var(--fm-red)]';
    case 'award': return 'bg-[var(--fm-yellow)]/15 text-[var(--fm-yellow)]';
    default: return 'bg-[var(--fm-surface2)] text-[var(--fm-text-muted)]';
  }
}

function getOrdinal(n: number): string {
  if (n >= 11 && n <= 13) return 'th';
  switch (n % 10) {
    case 1: return 'st';
    case 2: return 'nd';
    case 3: return 'rd';
    default: return 'th';
  }
}

function formatMoney(m: number): string {
  if (m >= 1) return `\u20AC${m.toFixed(1)}M`;
  return `\u20AC${(m * 1000).toFixed(0)}K`;
}
