import { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowUpDown, Search, Heart, Zap, Star, AlertTriangle,
  Shield, Check, ChevronRight, X,
} from 'lucide-react';
import type { PlayerDetail } from '../types';

type SortKey = 'name' | 'position' | 'overall' | 'age' | 'fitness' | 'morale' | 'form';

const posGroups: Record<string, string[]> = {
  ALL: [],
  GK: ['GK'],
  DEF: ['CB', 'LB', 'RB', 'LWB', 'RWB'],
  MID: ['CDM', 'CM', 'CAM', 'LM', 'RM'],
  FWD: ['LW', 'RW', 'CF', 'ST'],
};

const posColors: Record<string, { bg: string; text: string }> = {
  GK: { bg: 'bg-yellow-500/15', text: 'text-yellow-400' },
  CB: { bg: 'bg-blue-500/15', text: 'text-blue-400' },
  LB: { bg: 'bg-blue-500/15', text: 'text-blue-400' },
  RB: { bg: 'bg-blue-500/15', text: 'text-blue-400' },
  LWB: { bg: 'bg-blue-500/15', text: 'text-blue-400' },
  RWB: { bg: 'bg-blue-500/15', text: 'text-blue-400' },
  CDM: { bg: 'bg-emerald-500/15', text: 'text-emerald-400' },
  CM: { bg: 'bg-emerald-500/15', text: 'text-emerald-400' },
  CAM: { bg: 'bg-emerald-500/15', text: 'text-emerald-400' },
  LM: { bg: 'bg-emerald-500/15', text: 'text-emerald-400' },
  RM: { bg: 'bg-emerald-500/15', text: 'text-emerald-400' },
  LW: { bg: 'bg-red-500/15', text: 'text-red-400' },
  RW: { bg: 'bg-red-500/15', text: 'text-red-400' },
  CF: { bg: 'bg-red-500/15', text: 'text-red-400' },
  ST: { bg: 'bg-red-500/15', text: 'text-red-400' },
};

function ovrColor(ovr: number) {
  if (ovr >= 85) return 'bg-emerald-500 text-white';
  if (ovr >= 78) return 'bg-blue-500 text-white';
  if (ovr >= 70) return 'bg-sky-500 text-white';
  if (ovr >= 62) return 'bg-amber-500 text-white';
  return 'bg-gray-500 text-white';
}

export default function Squad() {
  const { players, fetchSquad, loadingSquad } = useStore();
  const [sortKey, setSortKey] = useState<SortKey>('overall');
  const [sortAsc, setSortAsc] = useState(false);
  const [search, setSearch] = useState('');
  const [posGroup, setPosGroup] = useState('ALL');
  const [selectedPlayer, setSelectedPlayer] = useState<PlayerDetail | null>(null);
  const navigate = useNavigate();

  useEffect(() => { fetchSquad(); }, []);

  const filtered = useMemo(() => {
    let list = players;
    if (posGroup !== 'ALL') {
      const positions = posGroups[posGroup];
      list = list.filter(p => positions.includes(p.position));
    }
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(p => p.name.toLowerCase().includes(q));
    }
    return [...list].sort((a, b) => {
      const va = a[sortKey] ?? 0;
      const vb = b[sortKey] ?? 0;
      if (typeof va === 'string') return sortAsc ? va.localeCompare(vb as string) : (vb as string).localeCompare(va);
      return sortAsc ? (va as number) - (vb as number) : (vb as number) - (va as number);
    });
  }, [players, posGroup, search, sortKey, sortAsc]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  const avgOvr = players.length > 0 ? (players.reduce((s, p) => s + p.overall, 0) / players.length).toFixed(1) : '--';
  const avgAge = players.length > 0 ? (players.reduce((s, p) => s + p.age, 0) / players.length).toFixed(1) : '--';
  const totalWages = players.reduce((s, p) => s + p.wage, 0);

  const SortTh = ({ label, k, className = '' }: { label: string; k: SortKey; className?: string }) => (
    <th className={`px-3 py-2.5 text-left cursor-pointer select-none hover:text-[var(--fm-accent)] group ${className}`} onClick={() => toggleSort(k)}>
      <span className="flex items-center gap-1">
        {label}
        <ArrowUpDown size={10} className={sortKey === k ? 'text-[var(--fm-accent)]' : 'text-transparent group-hover:text-[var(--fm-text-muted)]'} />
      </span>
    </th>
  );

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      <h1 className="text-2xl font-bold tracking-tight mb-4">Squad</h1>

      {/* Summary bar */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        {[
          { label: 'Total Players', value: String(players.length), color: 'text-[var(--fm-accent)]' },
          { label: 'Avg Overall', value: avgOvr, color: 'text-[var(--fm-green)]' },
          { label: 'Avg Age', value: avgAge, color: 'text-[var(--fm-yellow)]' },
          { label: 'Total Wages/w', value: formatMoney(totalWages), color: 'text-[var(--fm-orange)]' },
        ].map(s => (
          <div key={s.label} className="card flex items-center gap-3 !py-3">
            <span className={`text-xl font-bold tabular-nums ${s.color}`}>{s.value}</span>
            <span className="text-xs text-[var(--fm-text-muted)]">{s.label}</span>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4">
        <div className="flex bg-[var(--fm-surface)] rounded-lg border border-[var(--fm-border)] overflow-hidden">
          {Object.keys(posGroups).map(g => (
            <button
              key={g}
              onClick={() => setPosGroup(g)}
              className={`px-3.5 py-1.5 text-xs font-semibold transition-all ${
                posGroup === g
                  ? 'bg-[var(--fm-accent)] text-white'
                  : 'text-[var(--fm-text-muted)] hover:text-[var(--fm-text)] hover:bg-[var(--fm-surface2)]'
              }`}
            >
              {g}
            </button>
          ))}
        </div>
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--fm-text-muted)]" />
          <input type="text" placeholder="Search players..." value={search} onChange={e => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-[var(--fm-surface)] border border-[var(--fm-border)] text-sm" />
        </div>
        <span className="text-xs text-[var(--fm-text-muted)] ml-auto">{filtered.length} shown</span>
      </div>

      {/* Table */}
      <div className="card !p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--fm-surface2)] text-[10px] uppercase tracking-wider text-[var(--fm-text-muted)]">
              <SortTh label="Player" k="name" className="w-[200px]" />
              <SortTh label="Pos" k="position" />
              <SortTh label="OVR" k="overall" />
              <SortTh label="Age" k="age" />
              <th className="px-3 py-2.5 text-left">Status</th>
              <SortTh label="Fitness" k="fitness" />
              <SortTh label="Morale" k="morale" />
              <SortTh label="Form" k="form" />
              <th className="px-3 py-2.5 text-left">G / A</th>
              <th className="px-3 py-2.5 w-8"></th>
            </tr>
          </thead>
          <tbody>
            {loadingSquad ? (
              <tr><td colSpan={10} className="px-3 py-12 text-center text-[var(--fm-text-muted)]">
                <span className="inline-block w-5 h-5 border-2 border-[var(--fm-accent)]/30 border-t-[var(--fm-accent)] rounded-full animate-spin" />
              </td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={10} className="px-3 py-12 text-center text-[var(--fm-text-muted)]">No players found</td></tr>
            ) : filtered.map((p, i) => {
              const pc = posColors[p.position] ?? { bg: 'bg-gray-500/15', text: 'text-gray-400' };
              return (
                <tr key={p.id} onClick={() => setSelectedPlayer(p)}
                  className={`border-t border-[var(--fm-border)] cursor-pointer group transition-all
                    hover:bg-[var(--fm-accent)]/5 hover:shadow-[0_2px_8px_rgba(0,0,0,0.12)]
                    ${selectedPlayer?.id === p.id ? 'bg-[var(--fm-accent)]/8' : i % 2 === 1 ? 'bg-[var(--fm-surface2)]/20' : ''}`}
                >
                  <td className="px-3 py-2">
                    <span className="font-medium text-[var(--fm-text)] group-hover:text-[var(--fm-accent)]">{p.name}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${pc.bg} ${pc.text}`}>{p.position}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold ${ovrColor(p.overall)}`}>
                      {p.overall}
                    </span>
                  </td>
                  <td className="px-3 py-2 tabular-nums text-[var(--fm-text-muted)]">{p.age}</td>
                  <td className="px-3 py-2">
                    {p.injured_weeks > 0 ? (
                      <span className="inline-flex items-center gap-1 text-[var(--fm-red)] text-xs">
                        <AlertTriangle size={11} /> {p.injured_weeks}w
                      </span>
                    ) : p.suspended_matches > 0 ? (
                      <span className="inline-flex items-center gap-1 text-[var(--fm-yellow)] text-xs">
                        <Shield size={11} /> {p.suspended_matches}m
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[var(--fm-green)] text-xs">
                        <Check size={11} />
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2"><MiniBar value={p.fitness} /></td>
                  <td className="px-3 py-2"><MiniBar value={p.morale} /></td>
                  <td className="px-3 py-2"><MiniBar value={p.form} /></td>
                  <td className="px-3 py-2 tabular-nums text-[var(--fm-text-muted)]">
                    <span className="text-[var(--fm-text)]">{p.goals_season}</span>
                    <span className="text-[var(--fm-border)] mx-0.5">/</span>
                    <span>{p.assists_season}</span>
                  </td>
                  <td className="px-3 py-2">
                    <ChevronRight size={14} className="text-[var(--fm-border)] group-hover:text-[var(--fm-accent)]" />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Slide-in Player Panel */}
      <AnimatePresence>
        {selectedPlayer && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/40 z-40"
              onClick={() => setSelectedPlayer(null)}
            />
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 30, stiffness: 300 }}
              className="fixed right-0 top-0 h-full w-[420px] bg-[var(--fm-surface)] border-l border-[var(--fm-border)] z-50 overflow-y-auto shadow-2xl"
            >
              <PlayerPanel
                player={selectedPlayer}
                onClose={() => setSelectedPlayer(null)}
                onViewFull={() => {
                  const id = selectedPlayer.id;
                  setSelectedPlayer(null);
                  navigate(`/squad/${id}`);
                }}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function PlayerPanel({ player: p, onClose, onViewFull }: { player: PlayerDetail; onClose: () => void; onViewFull: () => void }) {
  const pc = posColors[p.position] ?? { bg: 'bg-gray-500/15', text: 'text-gray-400' };

  return (
    <div className="p-5">
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div className="flex items-start gap-3">
          <div className={`w-14 h-14 rounded-xl flex items-center justify-center text-white text-xl font-bold ${ovrColor(p.overall)}`}>
            {p.overall}
          </div>
          <div>
            <h2 className="text-lg font-bold leading-tight">{p.name}</h2>
            <div className="flex items-center gap-2 mt-1">
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${pc.bg} ${pc.text}`}>{p.position}</span>
              <span className="text-xs text-[var(--fm-text-muted)]">Age {p.age}</span>
              {p.nationality && <span className="text-xs text-[var(--fm-text-muted)]">{p.nationality}</span>}
            </div>
            <p className="text-[10px] text-[var(--fm-text-muted)] mt-0.5">Potential: {p.potential}</p>
          </div>
        </div>
        <button onClick={onClose} className="p-1 rounded hover:bg-[var(--fm-surface2)]">
          <X size={18} className="text-[var(--fm-text-muted)]" />
        </button>
      </div>

      {/* Status bars */}
      <div className="grid grid-cols-2 gap-2.5 mb-5">
        <MiniStatBar label="Fitness" value={p.fitness} icon={Zap} />
        <MiniStatBar label="Morale" value={p.morale} icon={Heart} />
        <MiniStatBar label="Form" value={p.form} icon={Star} />
        <MiniStatBar label="Trust" value={p.trust_in_manager} icon={Heart} />
      </div>

      {/* Radar Chart */}
      <div className="mb-5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-2">Attributes</h3>
        <div className="flex justify-center bg-[var(--fm-surface2)] rounded-xl py-3">
          <RadarChart
            data={[
              { label: 'PAC', value: p.pace },
              { label: 'SHO', value: p.shooting },
              { label: 'PAS', value: p.passing },
              { label: 'DRI', value: p.dribbling },
              { label: 'DEF', value: p.defending },
              { label: 'PHY', value: p.physical },
            ]}
            size={200}
          />
        </div>
      </div>

      {/* Season Stats */}
      <div className="mb-5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-2">Season Stats</h3>
        <div className="grid grid-cols-3 gap-2">
          <StatCard label="Goals" value={p.goals_season} />
          <StatCard label="Assists" value={p.assists_season} />
          <StatCard label="Minutes" value={p.minutes_season} />
        </div>
      </div>

      {/* Contract info */}
      <div className="mb-5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-2">Contract</h3>
        <div className="grid grid-cols-2 gap-y-2 text-xs bg-[var(--fm-surface2)] rounded-lg p-3">
          <span className="text-[var(--fm-text-muted)]">Value</span>
          <span className="font-semibold text-right">{formatMoney(p.market_value)}</span>
          <span className="text-[var(--fm-text-muted)]">Wage</span>
          <span className="font-semibold text-right">{formatMoney(p.wage)}/w</span>
          <span className="text-[var(--fm-text-muted)]">Expires</span>
          <span className="font-semibold text-right">Season {p.contract_expiry}</span>
          <span className="text-[var(--fm-text-muted)]">Role</span>
          <span className="font-semibold text-right capitalize">{p.squad_role.replace('_', ' ')}</span>
        </div>
      </div>

      <button
        onClick={onViewFull}
        className="w-full py-2.5 rounded-lg bg-[var(--fm-accent)] text-white text-sm font-semibold hover:brightness-110 flex items-center justify-center gap-2"
      >
        View Full Profile <ChevronRight size={14} />
      </button>
    </div>
  );
}

function MiniStatBar({ label, value, icon: Icon }: { label: string; value: number; icon: React.ElementType }) {
  const color = value > 75 ? 'var(--fm-green)' : value > 50 ? 'var(--fm-yellow)' : 'var(--fm-red)';
  return (
    <div className="p-2.5 rounded-lg bg-[var(--fm-surface2)]">
      <div className="flex items-center gap-1 mb-1.5">
        <Icon size={11} style={{ color }} />
        <span className="text-[10px] text-[var(--fm-text-muted)]">{label}</span>
        <span className="text-xs font-bold ml-auto tabular-nums" style={{ color }}>{value.toFixed(0)}</span>
      </div>
      <div className="h-1 bg-[var(--fm-bg)] rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${value}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="p-3 rounded-lg bg-[var(--fm-surface2)] text-center">
      <p className="text-lg font-bold tabular-nums">{value}</p>
      <p className="text-[10px] text-[var(--fm-text-muted)]">{label}</p>
    </div>
  );
}

function RadarChart({ data, size }: { data: { label: string; value: number }[]; size: number }) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.35;
  const n = data.length;
  const levels = 5;

  const getPoint = (i: number, radius: number) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    return { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
  };

  const gridLines = Array.from({ length: levels }, (_, l) => {
    const lr = (r * (l + 1)) / levels;
    return data.map((_, i) => getPoint(i, lr)).map(p => `${p.x},${p.y}`).join(' ');
  });

  const dataPoints = data.map((d, i) => getPoint(i, (d.value / 100) * r));
  const dataPath = dataPoints.map(p => `${p.x},${p.y}`).join(' ');

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {gridLines.map((pts, i) => (
        <polygon key={i} points={pts} fill="none" stroke="var(--fm-border)" strokeWidth="0.5" opacity={0.6} />
      ))}
      {data.map((_, i) => {
        const p = getPoint(i, r);
        return <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="var(--fm-border)" strokeWidth="0.5" opacity={0.4} />;
      })}
      <polygon points={dataPath} fill="var(--fm-accent)" fillOpacity="0.15" stroke="var(--fm-accent)" strokeWidth="1.5" />
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3" fill="var(--fm-accent)" />
      ))}
      {data.map((d, i) => {
        const p = getPoint(i, r + 18);
        return (
          <g key={i}>
            <text x={p.x} y={p.y - 5} textAnchor="middle" dominantBaseline="middle"
              fill="var(--fm-text-muted)" fontSize="9" fontWeight="600">{d.label}</text>
            <text x={p.x} y={p.y + 7} textAnchor="middle" dominantBaseline="middle"
              fill="var(--fm-text)" fontSize="10" fontWeight="700">{d.value}</text>
          </g>
        );
      })}
    </svg>
  );
}

function MiniBar({ value }: { value: number }) {
  const color = value > 75 ? 'var(--fm-green)' : value > 50 ? 'var(--fm-yellow)' : 'var(--fm-red)';
  return (
    <div className="flex items-center gap-1.5 w-16">
      <div className="flex-1 h-1 bg-[var(--fm-surface2)] rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${value}%`, backgroundColor: color }} />
      </div>
      <span className="text-[10px] tabular-nums w-5 text-right text-[var(--fm-text-muted)]">{value.toFixed(0)}</span>
    </div>
  );
}

function formatMoney(m: number): string {
  if (m >= 1) return `\u20AC${m.toFixed(1)}M`;
  return `\u20AC${(m * 1000).toFixed(0)}K`;
}
