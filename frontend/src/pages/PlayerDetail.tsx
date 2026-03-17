import { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import { motion } from 'framer-motion';
import { ArrowLeft, Star, Heart, Zap, Shield, FileText } from 'lucide-react';

const attrGroups = [
  { label: 'Pace', key: 'pace' },
  { label: 'Shooting', key: 'shooting' },
  { label: 'Passing', key: 'passing' },
  { label: 'Dribbling', key: 'dribbling' },
  { label: 'Defending', key: 'defending' },
  { label: 'Physical', key: 'physical' },
];

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
  if (ovr >= 85) return 'bg-emerald-500';
  if (ovr >= 78) return 'bg-blue-500';
  if (ovr >= 70) return 'bg-sky-500';
  if (ovr >= 62) return 'bg-amber-500';
  return 'bg-gray-500';
}

function attrColor(val: number): string {
  if (val >= 80) return 'var(--fm-green)';
  if (val >= 60) return 'var(--fm-accent)';
  if (val >= 40) return 'var(--fm-yellow)';
  return 'var(--fm-red)';
}

export default function PlayerDetailPage() {
  const { playerId } = useParams();
  const { selectedPlayer, fetchPlayer, clearSelectedPlayer } = useStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (playerId) fetchPlayer(Number(playerId));
    return () => clearSelectedPlayer();
  }, [playerId]);

  const p = selectedPlayer;
  if (!p) {
    return (
      <div className="flex items-center justify-center h-64 text-[var(--fm-text-muted)]">
        <span className="inline-block w-5 h-5 border-2 border-[var(--fm-accent)]/30 border-t-[var(--fm-accent)] rounded-full animate-spin mr-3" />
        Loading player...
      </div>
    );
  }

  const pc = posColors[p.position] ?? { bg: 'bg-gray-500/15', text: 'text-gray-400' };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      <button onClick={() => navigate('/squad')} className="flex items-center gap-1.5 text-[var(--fm-accent)] mb-4 hover:underline text-sm font-medium">
        <ArrowLeft size={16} /> Back to Squad
      </button>

      {/* Header Card */}
      <div className="card mb-4">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-4">
            {/* Rating badge */}
            <div className={`w-16 h-16 rounded-xl flex flex-col items-center justify-center text-white shadow-lg ${ovrColor(p.overall)}`}>
              <span className="text-2xl font-black leading-none">{p.overall}</span>
              <span className="text-[9px] font-semibold opacity-80">OVR</span>
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">{p.name}</h1>
              <div className="flex items-center gap-2 mt-1.5">
                <span className={`px-2.5 py-0.5 rounded text-[11px] font-bold ${pc.bg} ${pc.text}`}>{p.position}</span>
                <span className="text-sm text-[var(--fm-text-muted)]">Age {p.age}</span>
                {p.nationality && <span className="text-sm text-[var(--fm-text-muted)]">{p.nationality}</span>}
              </div>
            </div>
          </div>
          <div className="text-right">
            <p className="text-sm text-[var(--fm-text-muted)]">Potential</p>
            <p className="text-2xl font-bold text-[var(--fm-accent)] tabular-nums">{p.potential}</p>
          </div>
        </div>

        {/* Status bars */}
        <div className="grid grid-cols-4 gap-3 mt-5">
          <StatusBar label="Fitness" value={p.fitness} icon={Zap} />
          <StatusBar label="Morale" value={p.morale} icon={Heart} />
          <StatusBar label="Form" value={p.form} icon={Star} />
          <StatusBar label="Trust" value={p.trust_in_manager} icon={Shield} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        {/* Radar Chart + Attributes */}
        <div className="card">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-4">Attributes</h3>

          {/* Radar chart */}
          <div className="flex justify-center mb-5">
            <RadarChart
              data={attrGroups.map(g => ({
                label: g.label.slice(0, 3).toUpperCase(),
                value: (p as Record<string, unknown>)[g.key] as number,
              }))}
              size={220}
            />
          </div>

          {/* Attribute bars */}
          <div className="space-y-2.5">
            {attrGroups.map(g => {
              const val = (p as Record<string, unknown>)[g.key] as number;
              return (
                <div key={g.label} className="flex items-center gap-3">
                  <span className="text-xs text-[var(--fm-text-muted)] w-20">{g.label}</span>
                  <div className="flex-1 h-2 bg-[var(--fm-surface2)] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full animate-fill"
                      style={{
                        width: `${val}%`,
                        backgroundColor: attrColor(val),
                      }}
                    />
                  </div>
                  <span className="text-sm font-bold w-7 text-right tabular-nums" style={{ color: attrColor(val) }}>{val}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Season Stats + Contract */}
        <div className="space-y-4">
          {/* Season stats */}
          <div className="card">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-3">Season Stats</h3>
            <div className="grid grid-cols-3 gap-2 mb-2">
              <StatCard label="Goals" value={p.goals_season} />
              <StatCard label="Assists" value={p.assists_season} />
              <StatCard label="Minutes" value={p.minutes_season} />
            </div>
            <div className="grid grid-cols-2 gap-y-2 text-xs mt-3 pt-3 border-t border-[var(--fm-border)]">
              <span className="text-[var(--fm-text-muted)]">Squad Role</span>
              <span className="font-semibold text-right capitalize">{p.squad_role.replace('_', ' ')}</span>
              <span className="text-[var(--fm-text-muted)]">Fan Favorite</span>
              <span className="font-semibold text-right">{p.fan_favorite ? 'Yes' : 'No'}</span>
            </div>
          </div>

          {/* Contract */}
          <div className="card">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-3 flex items-center gap-2">
              <FileText size={13} /> Contract
            </h3>
            <div className="grid grid-cols-2 gap-y-2.5 text-sm">
              <span className="text-[var(--fm-text-muted)]">Market Value</span>
              <span className="font-bold text-right text-[var(--fm-green)]">{formatMoney(p.market_value)}</span>
              <span className="text-[var(--fm-text-muted)]">Wage</span>
              <span className="font-bold text-right">{formatMoney(p.wage)}/w</span>
              <span className="text-[var(--fm-text-muted)]">Expires</span>
              <span className="font-semibold text-right">Season {p.contract_expiry}</span>
              {p.release_clause !== undefined && p.release_clause > 0 && (
                <>
                  <span className="text-[var(--fm-text-muted)]">Release Clause</span>
                  <span className="font-semibold text-right text-[var(--fm-orange)]">{formatMoney(p.release_clause)}</span>
                </>
              )}
            </div>
          </div>

          {/* Mental Profile */}
          <div className="card">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-3">Mental Profile</h3>
            <div className="grid grid-cols-3 gap-3">
              <MentalStat label="Composure" value={p.composure} />
              <MentalStat label="Consistency" value={p.consistency} />
              <MentalStat label="Big Match" value={p.big_match} />
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function StatusBar({ label, value, icon: Icon }: { label: string; value: number; icon: React.ElementType }) {
  const color = value > 75 ? 'var(--fm-green)' : value > 50 ? 'var(--fm-yellow)' : 'var(--fm-red)';
  return (
    <div className="p-3 rounded-lg bg-[var(--fm-surface2)]">
      <div className="flex items-center gap-1.5 mb-2">
        <Icon size={12} style={{ color }} />
        <span className="text-[10px] text-[var(--fm-text-muted)]">{label}</span>
        <span className="text-sm font-bold ml-auto tabular-nums" style={{ color }}>{value.toFixed(0)}</span>
      </div>
      <div className="h-1.5 bg-[var(--fm-bg)] rounded-full overflow-hidden">
        <div className="h-full rounded-full animate-fill" style={{ width: `${value}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="p-3 rounded-lg bg-[var(--fm-surface2)] text-center">
      <p className="text-xl font-bold tabular-nums">{value}</p>
      <p className="text-[10px] text-[var(--fm-text-muted)]">{label}</p>
    </div>
  );
}

function MentalStat({ label, value }: { label: string; value: number }) {
  const color = value >= 80 ? 'text-[var(--fm-green)]' : value >= 60 ? 'text-[var(--fm-accent)]' : value >= 40 ? 'text-[var(--fm-yellow)]' : 'text-[var(--fm-red)]';
  return (
    <div className="text-center p-2 rounded-lg bg-[var(--fm-surface2)]">
      <p className={`text-lg font-bold tabular-nums ${color}`}>{value}</p>
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
      <polygon points={dataPath} fill="var(--fm-accent)" fillOpacity="0.15" stroke="var(--fm-accent)" strokeWidth="2" />
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3.5" fill="var(--fm-accent)" stroke="var(--fm-surface)" strokeWidth="1.5" />
      ))}
      {data.map((d, i) => {
        const p = getPoint(i, r + 20);
        return (
          <g key={i}>
            <text x={p.x} y={p.y - 6} textAnchor="middle" dominantBaseline="middle"
              fill="var(--fm-text-muted)" fontSize="9" fontWeight="600">{d.label}</text>
            <text x={p.x} y={p.y + 6} textAnchor="middle" dominantBaseline="middle"
              fill="var(--fm-text)" fontSize="11" fontWeight="700">{d.value}</text>
          </g>
        );
      })}
    </svg>
  );
}

function formatMoney(m: number): string {
  if (m >= 1) return `\u20AC${m.toFixed(1)}M`;
  return `\u20AC${(m * 1000).toFixed(0)}K`;
}
