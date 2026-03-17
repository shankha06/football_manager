import { useState, useEffect, useRef } from 'react';
import { useStore } from '../store';
import { useMatchWebSocket } from '../hooks/useWebSocket';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Play, SkipForward, Trophy, Target, BarChart3, Clock,
} from 'lucide-react';
import type { WSMessage } from '../types';
import * as api from '../api/client';
import type { NextFixture } from '../api/client';

export default function MatchDay() {
  const { currentMatch, simulateMatch, loading, clearMatch, club } = useStore();
  const [nextFixture, setNextFixture] = useState<NextFixture | null>(null);
  const [commentary, setCommentary] = useState<{ minute: number; text: string; type: string }[]>([]);
  const [liveStats, setLiveStats] = useState<Record<string, unknown>>({});
  const [matchEnded, setMatchEnded] = useState(false);
  const [liveScore, setLiveScore] = useState<{ home: number; away: number }>({ home: 0, away: 0 });
  const [liveMinute, setLiveMinute] = useState(0);
  const [goalFlash, setGoalFlash] = useState(false);
  const commentaryEndRef = useRef<HTMLDivElement>(null);

  const ws = useMatchWebSocket({
    onMessage: (msg: WSMessage) => {
      const d = msg.data as Record<string, unknown> | undefined;
      if (msg.type === 'commentary' || msg.type === 'goal' || msg.type === 'card' || msg.type === 'substitution') {
        setCommentary(prev => [...prev, { minute: msg.minute ?? 0, text: msg.text ?? '', type: msg.type }]);
        if (msg.minute) setLiveMinute(msg.minute);
      }
      if (msg.type === 'goal' && d) {
        setGoalFlash(true);
        setTimeout(() => setGoalFlash(false), 1500);
        if (d.home_goals !== undefined) {
          setLiveScore({ home: d.home_goals as number, away: d.away_goals as number });
        }
      }
      if (msg.type === 'stats_update' && d) {
        setLiveStats(d);
        if (d.home_goals !== undefined) {
          setLiveScore({ home: d.home_goals as number, away: d.away_goals as number });
        }
      }
      if (msg.type === 'match_start' && d) {
        setNextFixture(prev => prev ?? {
          fixture_id: 0, matchday: d.matchday as number ?? 0,
          home_club: d.home as string ?? 'Home', away_club: d.away as string ?? 'Away',
          home_club_id: 0, away_club_id: 0, is_home: true,
        });
      }
      if (msg.type === 'match_end') {
        setMatchEnded(true);
        if (d) setLiveStats(d);
      }
    },
  });

  useEffect(() => {
    if (commentaryEndRef.current) {
      commentaryEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [commentary]);

  const handleSimulate = async () => {
    clearMatch();
    setCommentary([]);
    setLiveStats({});
    setMatchEnded(false);
    setLiveScore({ home: 0, away: 0 });
    setLiveMinute(0);
    await simulateMatch();
    setMatchEnded(true);
  };

  const handleLiveMatch = () => {
    setCommentary([]);
    setLiveStats({});
    setMatchEnded(false);
    setLiveScore({ home: 0, away: 0 });
    setLiveMinute(0);
    ws.connect();
    ws.startMatch();
  };

  // Fetch next fixture on mount
  useEffect(() => {
    api.getNextFixture().then(setNextFixture).catch(() => {});
  }, []);

  const isLive = ws.connected && !matchEnded;
  const hasCommentary = commentary.length > 0;
  const showPreMatch = !currentMatch && !ws.connected && !hasCommentary;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      {/* Goal flash overlay */}
      <AnimatePresence>
        {goalFlash && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-[var(--fm-green)]/10 pointer-events-none z-50 screen-flash"
          />
        )}
      </AnimatePresence>

      <h1 className="text-2xl font-bold tracking-tight mb-4">Match Day</h1>

      {/* Pre-match state */}
      {showPreMatch && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
          {/* Fixture card */}
          <div className="card mb-6">
            {nextFixture ? (
              <div className="flex items-center justify-center py-8">
                <div className="text-center flex-1">
                  <div
                    className="w-16 h-16 rounded-xl flex items-center justify-center text-white font-bold text-lg mx-auto mb-3 shadow-lg"
                    style={{ backgroundColor: club?.primary_color || 'var(--fm-accent)' }}
                  >
                    {nextFixture.home_club.slice(0, 3).toUpperCase()}
                  </div>
                  <p className="font-bold text-lg">{nextFixture.home_club}</p>
                  <p className="text-xs text-[var(--fm-text-muted)]">Home</p>
                </div>

                <div className="px-8 text-center">
                  <div className="text-5xl font-black text-[var(--fm-text-muted)] tracking-wide">vs</div>
                  <p className="text-xs text-[var(--fm-text-muted)] mt-2">
                    {club?.league_name} &middot; Matchday {nextFixture.matchday}
                  </p>
                </div>

                <div className="text-center flex-1">
                  <div className="w-16 h-16 rounded-xl bg-[var(--fm-surface2)] flex items-center justify-center text-[var(--fm-text)] font-bold text-lg mx-auto mb-3 shadow-lg">
                    {nextFixture.away_club.slice(0, 3).toUpperCase()}
                  </div>
                  <p className="font-bold text-lg">{nextFixture.away_club}</p>
                  <p className="text-xs text-[var(--fm-text-muted)]">Away</p>
                </div>
              </div>
            ) : (
              <div className="py-12 text-center text-[var(--fm-text-muted)]">Loading fixture...</div>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex gap-4 justify-center">
            <button
              onClick={handleSimulate}
              disabled={loading}
              className="px-8 py-4 bg-[var(--fm-accent)] text-white rounded-xl font-semibold text-base
                hover:brightness-110 disabled:opacity-50 flex items-center gap-3 shadow-lg shadow-blue-500/20"
            >
              {loading ? (
                <span className="inline-block w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <SkipForward size={20} />
              )}
              {loading ? 'Simulating...' : 'Quick Simulate'}
            </button>
            <button
              onClick={handleLiveMatch}
              className="px-8 py-4 bg-[var(--fm-green)] text-white rounded-xl font-semibold text-base
                hover:brightness-110 flex items-center gap-3 shadow-lg shadow-green-500/20"
            >
              <Play size={20} />
              Watch Live
            </button>
          </div>
        </motion.div>
      )}

      {/* Live match view */}
      {(isLive || (hasCommentary && !currentMatch)) && (
        <div>
          {/* Scoreboard */}
          <div className="card mb-4">
            <div className="flex items-center justify-center py-4">
              <div className="text-right flex-1">
                <p className="text-lg font-bold">{club?.name ?? 'Home'}</p>
              </div>
              <div className="px-8 text-center">
                <div className="flex items-center gap-4">
                  <span className="text-5xl font-black tabular-nums">{liveScore.home}</span>
                  <span className="text-2xl text-[var(--fm-text-muted)]">-</span>
                  <span className="text-5xl font-black tabular-nums">{liveScore.away}</span>
                </div>
                <div className="flex items-center justify-center gap-2 mt-2">
                  {isLive && <div className="w-2 h-2 rounded-full bg-[var(--fm-green)] pulse-dot" />}
                  <span className={`text-sm font-semibold tabular-nums ${isLive ? 'text-[var(--fm-green)]' : 'text-[var(--fm-text-muted)]'}`}>
                    {matchEnded ? 'Full Time' : `${liveMinute}'`}
                  </span>
                </div>
              </div>
              <div className="text-left flex-1">
                <p className="text-lg font-bold">{nextFixture?.away_club ?? 'Away'}</p>
              </div>
            </div>
          </div>

          {/* Commentary + Stats */}
          <div className="grid grid-cols-3 gap-4">
            {/* Commentary feed */}
            <div className="col-span-2 card max-h-[500px] overflow-y-auto !p-0">
              <div className="sticky top-0 bg-[var(--fm-surface)] border-b border-[var(--fm-border)] px-4 py-2.5 z-10">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)]">Commentary</h3>
              </div>
              <div className="p-4 space-y-1">
                {commentary.map((c, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.2 }}
                    className={`flex gap-3 text-sm py-1.5 px-2 rounded ${
                      c.type === 'goal'
                        ? 'bg-[var(--fm-green)]/10 border-l-2 border-[var(--fm-green)]'
                        : c.type === 'card'
                        ? 'bg-[var(--fm-yellow)]/5 border-l-2 border-[var(--fm-yellow)]'
                        : 'hover:bg-[var(--fm-surface2)]'
                    }`}
                  >
                    <span className="text-[var(--fm-text-muted)] w-8 text-right flex-shrink-0 tabular-nums font-semibold text-xs pt-0.5">
                      {c.minute}'
                    </span>
                    <span className={
                      c.type === 'goal' ? 'text-[var(--fm-green)] font-bold' :
                      c.type === 'card' ? 'text-[var(--fm-yellow)]' :
                      'text-[var(--fm-text)]'
                    }>
                      {c.text}
                    </span>
                  </motion.div>
                ))}
                {commentary.length === 0 && (
                  <p className="text-[var(--fm-text-muted)] text-center py-8">Waiting for match to start...</p>
                )}
                <div ref={commentaryEndRef} />
              </div>
            </div>

            {/* Live Stats */}
            <div className="card max-h-[500px] overflow-y-auto">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-4">
                {matchEnded ? 'Final Stats' : 'Live Stats'}
              </h3>
              {Object.keys(liveStats).length > 0 ? (
                <div className="space-y-2">
                  {/* Attacking */}
                  <p className="text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)] font-semibold pt-1">Attacking</p>
                  <LiveStatRow label="Possession" home={`${liveStats.home_possession ?? 50}%`} away={`${liveStats.away_possession ?? 50}%`} homeVal={Number(liveStats.home_possession ?? 50)} />
                  <LiveStatRow label="Shots" home={liveStats.home_shots ?? 0} away={liveStats.away_shots ?? 0} />
                  <LiveStatRow label="On Target" home={liveStats.home_shots_on_target ?? 0} away={liveStats.away_shots_on_target ?? 0} />
                  <LiveStatRow label="xG" home={liveStats.home_xg ?? 0} away={liveStats.away_xg ?? 0} />
                  <LiveStatRow label="Big Chances" home={liveStats.home_big_chances ?? 0} away={liveStats.away_big_chances ?? 0} />
                  <LiveStatRow label="Key Passes" home={liveStats.home_key_passes ?? 0} away={liveStats.away_key_passes ?? 0} />
                  {/* Passing */}
                  <p className="text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)] font-semibold pt-2">Passing</p>
                  <LiveStatRow label="Passes" home={liveStats.home_passes_completed ?? 0} away={liveStats.away_passes_completed ?? 0} />
                  <LiveStatRow label="Pass Accuracy" home={`${liveStats.home_pass_accuracy ?? 0}%`} away={`${liveStats.away_pass_accuracy ?? 0}%`} homeVal={Number(liveStats.home_pass_accuracy ?? 50)} />
                  <LiveStatRow label="Crosses" home={liveStats.home_crosses ?? 0} away={liveStats.away_crosses ?? 0} />
                  {/* Defending */}
                  <p className="text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)] font-semibold pt-2">Defending</p>
                  <LiveStatRow label="Tackles Won" home={liveStats.home_tackles ?? 0} away={liveStats.away_tackles ?? 0} />
                  <LiveStatRow label="Interceptions" home={liveStats.home_interceptions ?? 0} away={liveStats.away_interceptions ?? 0} />
                  <LiveStatRow label="Clearances" home={liveStats.home_clearances ?? 0} away={liveStats.away_clearances ?? 0} />
                  <LiveStatRow label="Aerials Won" home={liveStats.home_aerials_won ?? 0} away={liveStats.away_aerials_won ?? 0} />
                  {/* Discipline */}
                  <p className="text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)] font-semibold pt-2">Discipline</p>
                  <LiveStatRow label="Fouls" home={liveStats.home_fouls ?? 0} away={liveStats.away_fouls ?? 0} />
                  <LiveStatRow label="Offsides" home={liveStats.home_offsides ?? 0} away={liveStats.away_offsides ?? 0} />
                  <LiveStatRow label="Yellow Cards" home={liveStats.home_yellow_cards ?? 0} away={liveStats.away_yellow_cards ?? 0} />
                  <LiveStatRow label="Red Cards" home={liveStats.home_red_cards ?? 0} away={liveStats.away_red_cards ?? 0} />
                  {/* GK */}
                  <p className="text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)] font-semibold pt-2">Goalkeeping</p>
                  <LiveStatRow label="Saves" home={liveStats.home_saves ?? 0} away={liveStats.away_saves ?? 0} />
                </div>
              ) : (
                <p className="text-xs text-[var(--fm-text-muted)] text-center py-4">Stats will appear here</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Quick sim result */}
      {currentMatch && !ws.connected && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
          {/* Final Score */}
          <div className="card mb-4">
            <div className="text-center py-3">
              <p className="text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)] font-semibold mb-3">Full Time</p>
              <div className="flex items-center justify-center gap-8">
                <div className="text-right flex-1">
                  <p className="text-xl font-bold">{currentMatch.home_club}</p>
                  <p className="text-xs text-[var(--fm-text-muted)] mt-0.5">xG: {(currentMatch.home_xg ?? 0).toFixed(2)}</p>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-5xl font-black tabular-nums">{currentMatch.home_goals}</span>
                  <span className="text-xl text-[var(--fm-text-muted)]">-</span>
                  <span className="text-5xl font-black tabular-nums">{currentMatch.away_goals}</span>
                </div>
                <div className="text-left flex-1">
                  <p className="text-xl font-bold">{currentMatch.away_club}</p>
                  <p className="text-xs text-[var(--fm-text-muted)] mt-0.5">xG: {(currentMatch.away_xg ?? 0).toFixed(2)}</p>
                </div>
              </div>
              {currentMatch.motm_player_name && (
                <div className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--fm-yellow)]/10 border border-[var(--fm-yellow)]/20">
                  <Trophy size={14} className="text-[var(--fm-yellow)]" />
                  <span className="text-sm font-semibold text-[var(--fm-yellow)]">MOTM: {currentMatch.motm_player_name}</span>
                </div>
              )}
            </div>
          </div>

          {/* Stats comparison */}
          <div className="card mb-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-4 flex items-center gap-2">
              <BarChart3 size={14} /> Match Statistics
            </h3>
            <div className="space-y-3">
              {/* Attacking */}
              <p className="text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)] font-semibold pt-1">Attacking</p>
              <ComparisonBar label="Possession" homeVal={currentMatch.home_possession ?? 50} awayVal={100 - (currentMatch.home_possession ?? 50)} suffix="%" />
              <ComparisonBar label="Shots" homeVal={currentMatch.home_shots ?? 0} awayVal={currentMatch.away_shots ?? 0} />
              <ComparisonBar label="On Target" homeVal={currentMatch.home_shots_on_target ?? 0} awayVal={currentMatch.away_shots_on_target ?? 0} />
              <ComparisonBar label="xG" homeVal={Number((currentMatch.home_xg ?? 0).toFixed(2))} awayVal={Number((currentMatch.away_xg ?? 0).toFixed(2))} />
              <ComparisonBar label="Big Chances" homeVal={currentMatch.home_big_chances ?? 0} awayVal={currentMatch.away_big_chances ?? 0} />
              <ComparisonBar label="Key Passes" homeVal={currentMatch.home_key_passes ?? 0} awayVal={currentMatch.away_key_passes ?? 0} />

              {/* Passing */}
              <p className="text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)] font-semibold pt-2">Passing</p>
              <ComparisonBar label="Passes" homeVal={currentMatch.home_passes ?? 0} awayVal={currentMatch.away_passes ?? 0} />
              <ComparisonBar label="Pass Accuracy" homeVal={currentMatch.home_pass_accuracy ?? 0} awayVal={currentMatch.away_pass_accuracy ?? 0} suffix="%" />
              <ComparisonBar label="Crosses" homeVal={currentMatch.home_crosses ?? 0} awayVal={currentMatch.away_crosses ?? 0} />

              {/* Defending */}
              <p className="text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)] font-semibold pt-2">Defending</p>
              <ComparisonBar label="Tackles Won" homeVal={currentMatch.home_tackles ?? 0} awayVal={currentMatch.away_tackles ?? 0} />
              <ComparisonBar label="Interceptions" homeVal={currentMatch.home_interceptions ?? 0} awayVal={currentMatch.away_interceptions ?? 0} />
              <ComparisonBar label="Clearances" homeVal={currentMatch.home_clearances ?? 0} awayVal={currentMatch.away_clearances ?? 0} />
              <ComparisonBar label="Aerials Won" homeVal={currentMatch.home_aerials_won ?? 0} awayVal={currentMatch.away_aerials_won ?? 0} />

              {/* Discipline */}
              <p className="text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)] font-semibold pt-2">Discipline</p>
              <ComparisonBar label="Fouls" homeVal={currentMatch.home_fouls ?? 0} awayVal={currentMatch.away_fouls ?? 0} />
              <ComparisonBar label="Offsides" homeVal={currentMatch.home_offsides ?? 0} awayVal={currentMatch.away_offsides ?? 0} />
              <ComparisonBar label="Yellow Cards" homeVal={currentMatch.home_yellow_cards ?? 0} awayVal={currentMatch.away_yellow_cards ?? 0} />
              <ComparisonBar label="Red Cards" homeVal={currentMatch.home_red_cards ?? 0} awayVal={currentMatch.away_red_cards ?? 0} />

              {/* Goalkeeping */}
              <p className="text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)] font-semibold pt-2">Goalkeeping</p>
              <ComparisonBar label="Saves" homeVal={currentMatch.home_saves ?? 0} awayVal={currentMatch.away_saves ?? 0} />

              {currentMatch.attendance && (
                <div className="pt-2 border-t border-[var(--fm-border)] text-xs text-[var(--fm-text-muted)] flex justify-between">
                  <span>Attendance: {currentMatch.attendance.toLocaleString()}</span>
                  {currentMatch.weather && <span className="capitalize">{currentMatch.weather}</span>}
                </div>
              )}
            </div>
          </div>

          {/* Event Timeline */}
          <div className="card">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-4 flex items-center gap-2">
              <Clock size={14} /> Match Events
            </h3>
            <div className="relative pl-6 border-l-2 border-[var(--fm-border)] space-y-0 max-h-[400px] overflow-y-auto">
              {currentMatch.events.map((e, i) => {
                const evType = e.event_type ?? e.type ?? '';
                const evText = e.description ?? e.text ?? `${evType} at ${e.minute}'`;
                const isGoal = evType === 'goal';
                const isCard = evType === 'yellow_card' || evType === 'red_card';
                return (
                  <div key={i} className="relative py-1.5">
                    <div className={`absolute -left-[25px] top-2.5 w-3 h-3 rounded-full border-2 border-[var(--fm-surface)] ${
                      isGoal ? 'bg-[var(--fm-green)]' :
                      isCard ? 'bg-[var(--fm-yellow)]' :
                      'bg-[var(--fm-border)]'
                    }`} />
                    <div className="flex items-start gap-3">
                      <span className="text-[var(--fm-text-muted)] text-xs tabular-nums font-semibold w-6 text-right flex-shrink-0">{e.minute}'</span>
                      <span className={`text-sm ${
                        isGoal ? 'text-[var(--fm-green)] font-bold' :
                        isCard ? 'text-[var(--fm-yellow)]' :
                        'text-[var(--fm-text)]'
                      }`}>
                        {evText}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}

function ComparisonBar({ label, homeVal, awayVal, suffix = '' }: { label: string; homeVal: number; awayVal: number; suffix?: string }) {
  const total = homeVal + awayVal || 1;
  const homePercent = (homeVal / total) * 100;
  const awayPercent = (awayVal / total) * 100;

  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="font-semibold tabular-nums">{homeVal}{suffix}</span>
        <span className="text-[var(--fm-text-muted)]">{label}</span>
        <span className="font-semibold tabular-nums">{awayVal}{suffix}</span>
      </div>
      <div className="flex gap-1 h-1.5">
        <div className="flex-1 bg-[var(--fm-surface2)] rounded-full overflow-hidden flex justify-end">
          <div className="h-full rounded-full bg-[var(--fm-accent)] animate-fill" style={{ width: `${homePercent}%` }} />
        </div>
        <div className="flex-1 bg-[var(--fm-surface2)] rounded-full overflow-hidden">
          <div className="h-full rounded-full bg-[var(--fm-red)] animate-fill" style={{ width: `${awayPercent}%` }} />
        </div>
      </div>
    </div>
  );
}

function LiveStatRow({ label, home, away, homeVal }: { label: string; home: string | number; away: string | number; homeVal?: number }) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="font-semibold tabular-nums w-12">{home}</span>
        <span className="text-[var(--fm-text-muted)] text-center flex-1">{label}</span>
        <span className="font-semibold tabular-nums w-12 text-right">{away}</span>
      </div>
      {homeVal !== undefined && (
        <div className="flex gap-0.5 h-1">
          <div className="flex-1 bg-[var(--fm-surface2)] rounded-full overflow-hidden flex justify-end">
            <div className="h-full bg-[var(--fm-accent)] rounded-full" style={{ width: `${homeVal}%` }} />
          </div>
          <div className="flex-1 bg-[var(--fm-surface2)] rounded-full overflow-hidden">
            <div className="h-full bg-[var(--fm-red)]/60 rounded-full" style={{ width: `${100 - homeVal}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}
