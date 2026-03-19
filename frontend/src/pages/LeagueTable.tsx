import { useEffect } from 'react';
import { useStore } from '../store';
import { motion } from 'framer-motion';
import { Trophy } from 'lucide-react';
import ClubBadge from '../components/common/ClubBadge';
import { LeagueLogo } from '../components/LeagueLogo';

export default function LeagueTable() {
  const { standings, club, fetchStandings } = useStore();

  useEffect(() => { fetchStandings(); }, []);

  const sorted = [...standings].sort(
    (a, b) => b.points - a.points || b.goal_difference - a.goal_difference || b.goals_for - a.goals_for,
  );

  const totalTeams = sorted.length;
  const relegationStart = totalTeams > 3 ? totalTeams - 2 : totalTeams;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      <div className="flex items-center gap-3 mb-6">
        <Trophy size={20} className="text-[var(--fm-yellow)]" />
        <h1 className="text-2xl font-bold tracking-tight">League Table</h1>
        {club?.league_name && (
          <div className="ml-auto flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--fm-surface)] border border-[var(--fm-border)] text-xs font-medium text-[var(--fm-text-muted)]">
            <LeagueLogo
              leagueId={club.league_name === 'Premier League' ? 1 : club.league_name === 'La Liga' ? 7 : club.league_name === 'Bundesliga' ? 12 : club.league_name === 'Serie A' ? 15 : club.league_name === 'Ligue 1' ? 20 : 1}
              leagueName={club.league_name}
              size={14}
            />
            {club.league_name}
          </div>
        )}
      </div>

      <div className="card !p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--fm-surface2)] text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)]">
              <th className="px-3 py-2.5 text-left w-10">#</th>
              <th className="px-3 py-2.5 text-left">Club</th>
              <th className="px-3 py-2.5 text-center w-10">P</th>
              <th className="px-3 py-2.5 text-center w-10">W</th>
              <th className="px-3 py-2.5 text-center w-10">D</th>
              <th className="px-3 py-2.5 text-center w-10">L</th>
              <th className="px-3 py-2.5 text-center w-10">GF</th>
              <th className="px-3 py-2.5 text-center w-10">GA</th>
              <th className="px-3 py-2.5 text-center w-10">GD</th>
              <th className="px-3 py-2.5 text-center w-12 font-bold">Pts</th>
              <th className="px-3 py-2.5 text-center">Form</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((s, i) => {
              const pos = i + 1;
              const isOurs = s.club_id === club?.id;
              const isPromotion = pos <= 4;
              const isRelegation = pos >= relegationStart;

              return (
                <tr
                  key={s.club_id}
                  className={`border-t border-[var(--fm-border)] transition-colors ${isOurs
                    ? 'bg-[var(--fm-accent)]/8'
                    : i % 2 === 1
                      ? 'bg-[var(--fm-surface2)]/20'
                      : 'hover:bg-[var(--fm-surface2)]'
                    }`}
                >
                  <td className="px-3 py-2.5 relative">
                    {/* Position indicator */}
                    {isPromotion && (
                      <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-[var(--fm-green)] rounded-r" />
                    )}
                    {isRelegation && (
                      <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-[var(--fm-red)] rounded-r" />
                    )}
                    <span className={`font-semibold tabular-nums ${isOurs ? 'text-[var(--fm-accent)]' : 'text-[var(--fm-text-muted)]'
                      }`}>
                      {pos}
                    </span>
                  </td>
                  <td className={`px-3 py-2.5 font-medium ${isOurs ? 'text-[var(--fm-accent)] font-bold' : ''}`}>
                    <div className="flex items-center gap-2">
                      <ClubBadge clubId={s.club_id} name={s.club_name} size={22} />
                      <span>{s.club_name}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-center tabular-nums text-[var(--fm-text-muted)]">{s.played}</td>
                  <td className="px-3 py-2.5 text-center tabular-nums">{s.won}</td>
                  <td className="px-3 py-2.5 text-center tabular-nums text-[var(--fm-text-muted)]">{s.drawn}</td>
                  <td className="px-3 py-2.5 text-center tabular-nums text-[var(--fm-text-muted)]">{s.lost}</td>
                  <td className="px-3 py-2.5 text-center tabular-nums">{s.goals_for}</td>
                  <td className="px-3 py-2.5 text-center tabular-nums text-[var(--fm-text-muted)]">{s.goals_against}</td>
                  <td className={`px-3 py-2.5 text-center tabular-nums font-semibold ${s.goal_difference > 0 ? 'text-[var(--fm-green)]' :
                    s.goal_difference < 0 ? 'text-[var(--fm-red)]' : 'text-[var(--fm-text-muted)]'
                    }`}>
                    {s.goal_difference > 0 ? `+${s.goal_difference}` : s.goal_difference}
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <span className={`text-base font-bold tabular-nums ${isOurs ? 'text-[var(--fm-accent)]' : ''}`}>
                      {s.points}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex gap-0.5 justify-center">
                      {(s.form || '').split('').slice(-5).map((r, j) => (
                        <span
                          key={j}
                          className={`w-5 h-5 flex items-center justify-center rounded text-[10px] font-bold ${r === 'W' ? 'bg-[var(--fm-green)]/15 text-[var(--fm-green)]' :
                            r === 'D' ? 'bg-[var(--fm-yellow)]/15 text-[var(--fm-yellow)]' :
                              'bg-[var(--fm-red)]/15 text-[var(--fm-red)]'
                            }`}
                        >
                          {r}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-3 text-[10px] text-[var(--fm-text-muted)]">
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-sm bg-[var(--fm-green)]" />
          <span>Champions League</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-sm bg-[var(--fm-red)]" />
          <span>Relegation</span>
        </div>
      </div>
    </motion.div>
  );
}
