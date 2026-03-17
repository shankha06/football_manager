import { useEffect, useState } from 'react';
import { useStore } from '../store';
import { motion } from 'framer-motion';
import { Shield, Swords, Gauge, ArrowLeftRight, ChevronUp, ChevronDown } from 'lucide-react';

const formations = ['4-4-2', '4-3-3', '4-2-3-1', '3-5-2', '5-3-2', '4-1-4-1', '3-4-3', '4-5-1'];
const mentalities = ['very_defensive', 'defensive', 'cautious', 'balanced', 'positive', 'attacking', 'very_attacking'];
const tempos = ['very_slow', 'slow', 'normal', 'fast', 'very_fast'];
const pressingLevels = ['low', 'standard', 'high', 'very_high'];
const passingStyles = ['very_short', 'short', 'mixed', 'direct', 'very_direct'];
const widths = ['very_narrow', 'narrow', 'normal', 'wide', 'very_wide'];
const defLines = ['deep', 'normal', 'high'];

const mentColors: Record<string, string> = {
  very_defensive: 'var(--fm-accent)',
  defensive: 'var(--fm-accent)',
  cautious: '#60a5fa',
  balanced: 'var(--fm-yellow)',
  positive: 'var(--fm-orange)',
  attacking: 'var(--fm-red)',
  very_attacking: 'var(--fm-red)',
};

const formationPositions: Record<string, { x: number; y: number; label: string }[]> = {
  '4-4-2': [
    { x: 50, y: 90, label: 'GK' },
    { x: 20, y: 72, label: 'LB' }, { x: 40, y: 75, label: 'CB' }, { x: 60, y: 75, label: 'CB' }, { x: 80, y: 72, label: 'RB' },
    { x: 20, y: 50, label: 'LM' }, { x: 40, y: 52, label: 'CM' }, { x: 60, y: 52, label: 'CM' }, { x: 80, y: 50, label: 'RM' },
    { x: 35, y: 25, label: 'ST' }, { x: 65, y: 25, label: 'ST' },
  ],
  '4-3-3': [
    { x: 50, y: 90, label: 'GK' },
    { x: 20, y: 72, label: 'LB' }, { x: 40, y: 75, label: 'CB' }, { x: 60, y: 75, label: 'CB' }, { x: 80, y: 72, label: 'RB' },
    { x: 30, y: 52, label: 'CM' }, { x: 50, y: 55, label: 'CM' }, { x: 70, y: 52, label: 'CM' },
    { x: 20, y: 25, label: 'LW' }, { x: 50, y: 22, label: 'ST' }, { x: 80, y: 25, label: 'RW' },
  ],
  '4-2-3-1': [
    { x: 50, y: 90, label: 'GK' },
    { x: 20, y: 72, label: 'LB' }, { x: 40, y: 75, label: 'CB' }, { x: 60, y: 75, label: 'CB' }, { x: 80, y: 72, label: 'RB' },
    { x: 35, y: 58, label: 'CDM' }, { x: 65, y: 58, label: 'CDM' },
    { x: 20, y: 40, label: 'LW' }, { x: 50, y: 38, label: 'CAM' }, { x: 80, y: 40, label: 'RW' },
    { x: 50, y: 20, label: 'ST' },
  ],
  '3-5-2': [
    { x: 50, y: 90, label: 'GK' },
    { x: 30, y: 75, label: 'CB' }, { x: 50, y: 76, label: 'CB' }, { x: 70, y: 75, label: 'CB' },
    { x: 15, y: 52, label: 'LWB' }, { x: 35, y: 55, label: 'CM' }, { x: 50, y: 52, label: 'CM' }, { x: 65, y: 55, label: 'CM' }, { x: 85, y: 52, label: 'RWB' },
    { x: 35, y: 25, label: 'ST' }, { x: 65, y: 25, label: 'ST' },
  ],
  '5-3-2': [
    { x: 50, y: 90, label: 'GK' },
    { x: 15, y: 72, label: 'LWB' }, { x: 32, y: 76, label: 'CB' }, { x: 50, y: 77, label: 'CB' }, { x: 68, y: 76, label: 'CB' }, { x: 85, y: 72, label: 'RWB' },
    { x: 30, y: 52, label: 'CM' }, { x: 50, y: 50, label: 'CM' }, { x: 70, y: 52, label: 'CM' },
    { x: 35, y: 25, label: 'ST' }, { x: 65, y: 25, label: 'ST' },
  ],
  '4-1-4-1': [
    { x: 50, y: 90, label: 'GK' },
    { x: 20, y: 72, label: 'LB' }, { x: 40, y: 75, label: 'CB' }, { x: 60, y: 75, label: 'CB' }, { x: 80, y: 72, label: 'RB' },
    { x: 50, y: 60, label: 'CDM' },
    { x: 20, y: 42, label: 'LM' }, { x: 40, y: 44, label: 'CM' }, { x: 60, y: 44, label: 'CM' }, { x: 80, y: 42, label: 'RM' },
    { x: 50, y: 22, label: 'ST' },
  ],
  '3-4-3': [
    { x: 50, y: 90, label: 'GK' },
    { x: 30, y: 75, label: 'CB' }, { x: 50, y: 76, label: 'CB' }, { x: 70, y: 75, label: 'CB' },
    { x: 20, y: 52, label: 'LM' }, { x: 40, y: 55, label: 'CM' }, { x: 60, y: 55, label: 'CM' }, { x: 80, y: 52, label: 'RM' },
    { x: 25, y: 25, label: 'LW' }, { x: 50, y: 22, label: 'ST' }, { x: 75, y: 25, label: 'RW' },
  ],
  '4-5-1': [
    { x: 50, y: 90, label: 'GK' },
    { x: 20, y: 72, label: 'LB' }, { x: 40, y: 75, label: 'CB' }, { x: 60, y: 75, label: 'CB' }, { x: 80, y: 72, label: 'RB' },
    { x: 15, y: 48, label: 'LM' }, { x: 35, y: 52, label: 'CM' }, { x: 50, y: 50, label: 'CM' }, { x: 65, y: 52, label: 'CM' }, { x: 85, y: 48, label: 'RM' },
    { x: 50, y: 22, label: 'ST' },
  ],
};

export default function Tactics() {
  const { tactics, fetchTactics, updateTactics, loadingTactics } = useStore();
  const [localTactics, setLocalTactics] = useState(tactics);

  useEffect(() => { fetchTactics(); }, []);
  useEffect(() => { setLocalTactics(tactics); }, [tactics]);

  const handleChange = (field: string, value: string | boolean) => {
    if (!localTactics) return;
    const updated = { ...localTactics, [field]: value };
    setLocalTactics(updated);
    updateTactics({ [field]: value });
  };

  if (loadingTactics || !localTactics) {
    return (
      <div className="flex items-center justify-center h-64 text-[var(--fm-text-muted)]">
        <span className="inline-block w-5 h-5 border-2 border-[var(--fm-accent)]/30 border-t-[var(--fm-accent)] rounded-full animate-spin mr-3" />
        Loading tactics...
      </div>
    );
  }

  const positions = formationPositions[localTactics.formation] ?? formationPositions['4-4-2'];
  const mentIdx = mentalities.indexOf(localTactics.mentality);

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      <h1 className="text-2xl font-bold tracking-tight mb-4">Tactics</h1>

      <div className="grid grid-cols-3 gap-4">
        {/* Formation Pitch */}
        <div className="col-span-2 card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)]">
              Formation
            </h3>
            <div className="flex gap-1.5">
              {formations.map(f => (
                <button
                  key={f}
                  onClick={() => handleChange('formation', f)}
                  className={`px-2 py-1 rounded text-[10px] font-semibold transition-all ${
                    localTactics.formation === f
                      ? 'bg-[var(--fm-accent)] text-white'
                      : 'bg-[var(--fm-surface2)] text-[var(--fm-text-muted)] hover:text-[var(--fm-text)]'
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          <svg viewBox="0 0 100 110" className="w-full max-w-lg mx-auto">
            {/* Pitch background with gradient */}
            <defs>
              <linearGradient id="grass" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#1a5c2e" />
                <stop offset="50%" stopColor="#1a472a" />
                <stop offset="100%" stopColor="#1a5c2e" />
              </linearGradient>
            </defs>
            <rect x="5" y="5" width="90" height="100" rx="2" fill="url(#grass)" />
            {/* Pitch markings */}
            <rect x="5" y="5" width="90" height="100" rx="2" fill="none" stroke="#2d7a3c" strokeWidth="0.5" />
            <circle cx="50" cy="55" r="10" fill="none" stroke="#2d7a3c" strokeWidth="0.3" />
            <circle cx="50" cy="55" r="0.8" fill="#2d7a3c" />
            <line x1="5" y1="55" x2="95" y2="55" stroke="#2d7a3c" strokeWidth="0.3" />
            {/* Penalty areas */}
            <rect x="25" y="5" width="50" height="15" fill="none" stroke="#2d7a3c" strokeWidth="0.3" />
            <rect x="35" y="5" width="30" height="6" fill="none" stroke="#2d7a3c" strokeWidth="0.3" />
            <rect x="25" y="90" width="50" height="15" fill="none" stroke="#2d7a3c" strokeWidth="0.3" />
            <rect x="35" y="99" width="30" height="6" fill="none" stroke="#2d7a3c" strokeWidth="0.3" />
            {/* Corner arcs */}
            <path d="M 5 8 A 3 3 0 0 1 8 5" fill="none" stroke="#2d7a3c" strokeWidth="0.3" />
            <path d="M 92 5 A 3 3 0 0 1 95 8" fill="none" stroke="#2d7a3c" strokeWidth="0.3" />
            <path d="M 5 102 A 3 3 0 0 0 8 105" fill="none" stroke="#2d7a3c" strokeWidth="0.3" />
            <path d="M 92 105 A 3 3 0 0 0 95 102" fill="none" stroke="#2d7a3c" strokeWidth="0.3" />

            {/* Players */}
            {positions.map((pos, i) => (
              <g key={i}>
                {/* Glow */}
                <circle cx={pos.x} cy={pos.y} r="5" fill="var(--fm-accent)" opacity="0.12" />
                {/* Player dot */}
                <circle cx={pos.x} cy={pos.y} r="3.5" fill="var(--fm-accent)" opacity="0.95" />
                {/* Position label */}
                <text x={pos.x} y={pos.y + 0.8} textAnchor="middle" fill="white" fontSize="2.2" fontWeight="bold" dominantBaseline="middle">
                  {pos.label}
                </text>
              </g>
            ))}
          </svg>
        </div>

        {/* Tactical Options */}
        <div className="space-y-4">
          {/* Mentality - visual scale */}
          <div className="card">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-3 flex items-center gap-2">
              <Gauge size={13} /> Mentality
            </h3>
            <div className="flex items-center gap-1.5 mb-2">
              <Shield size={13} className="text-[var(--fm-accent)]" />
              <div className="flex-1 flex gap-0.5">
                {mentalities.map((m, i) => (
                  <button
                    key={m}
                    onClick={() => handleChange('mentality', m)}
                    className="flex-1 h-2.5 rounded-sm transition-all"
                    style={{
                      backgroundColor: i <= mentIdx ? (mentColors[m] || 'var(--fm-accent)') : 'var(--fm-surface2)',
                      opacity: i <= mentIdx ? 1 : 0.4,
                    }}
                    title={m.replace(/_/g, ' ')}
                  />
                ))}
              </div>
              <Swords size={13} className="text-[var(--fm-red)]" />
            </div>
            <p className="text-xs text-center capitalize font-medium" style={{ color: mentColors[localTactics.mentality] }}>
              {localTactics.mentality.replace(/_/g, ' ')}
            </p>
          </div>

          {/* Scale options */}
          <div className="card space-y-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] flex items-center gap-2">
              <ChevronUp size={13} /> Attacking
            </h3>
            <ScaleOption label="Tempo" options={tempos} value={localTactics.tempo} onChange={v => handleChange('tempo', v)} />
            <ScaleOption label="Passing" options={passingStyles} value={localTactics.passing_style} onChange={v => handleChange('passing_style', v)} />
            <ScaleOption label="Width" options={widths} value={localTactics.width} onChange={v => handleChange('width', v)} />
          </div>

          <div className="card space-y-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] flex items-center gap-2">
              <ChevronDown size={13} /> Defensive
            </h3>
            <ScaleOption label="Pressing" options={pressingLevels} value={localTactics.pressing} onChange={v => handleChange('pressing', v)} />
            <ScaleOption label="Def. Line" options={defLines} value={localTactics.defensive_line} onChange={v => handleChange('defensive_line', v)} />
          </div>

          {/* Toggles */}
          <div className="card space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] flex items-center gap-2">
              <ArrowLeftRight size={13} /> General
            </h3>
            <TacticToggle label="Offside Trap" value={localTactics.offside_trap} onChange={v => handleChange('offside_trap', v)} />
            <TacticToggle label="Counter Attack" value={localTactics.counter_attack} onChange={v => handleChange('counter_attack', v)} />
            <TacticToggle label="Play Out From Back" value={localTactics.play_out_from_back} onChange={v => handleChange('play_out_from_back', v)} />
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function ScaleOption({ label, options, value, onChange }: {
  label: string; options: string[]; value: string; onChange: (v: string) => void;
}) {
  const idx = options.indexOf(value);
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-[var(--fm-text-muted)]">{label}</span>
        <span className="text-xs font-medium capitalize">{value.replace(/_/g, ' ')}</span>
      </div>
      <div className="flex gap-1">
        {options.map((o, i) => (
          <button
            key={o}
            onClick={() => onChange(o)}
            className={`flex-1 h-2 rounded-sm transition-all ${
              i <= idx
                ? 'bg-[var(--fm-accent)]'
                : 'bg-[var(--fm-surface2)]'
            }`}
            title={o.replace(/_/g, ' ')}
          />
        ))}
      </div>
    </div>
  );
}

function TacticToggle({ label, value, onChange }: {
  label: string; value: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between text-sm cursor-pointer group">
      <span className="text-[var(--fm-text-muted)] group-hover:text-[var(--fm-text)]">{label}</span>
      <button
        onClick={() => onChange(!value)}
        className={`w-10 h-5 rounded-full transition-colors relative ${value ? 'bg-[var(--fm-accent)]' : 'bg-[var(--fm-surface2)]'}`}
      >
        <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${value ? 'left-5.5' : 'left-0.5'}`} />
      </button>
    </label>
  );
}
