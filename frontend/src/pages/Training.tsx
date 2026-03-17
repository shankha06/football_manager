import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Dumbbell, Target, Shield, Zap, Brain, CircleDot, Crosshair,
  Check, AlertTriangle,
} from 'lucide-react';
import * as api from '../api/client';

const focusTypes = ['attacking', 'defending', 'physical', 'tactical', 'set_pieces', 'match_prep'] as const;
const intensities = ['recovery', 'light', 'normal', 'intense', 'double'] as const;

const focusMeta: Record<string, { icon: React.ElementType; desc: string; color: string }> = {
  attacking: { icon: Target, desc: 'Improve finishing, shooting, and movement in the final third', color: 'var(--fm-red)' },
  defending: { icon: Shield, desc: 'Work on tackling, positioning, and defensive shape', color: 'var(--fm-accent)' },
  physical: { icon: Zap, desc: 'Build stamina, strength, and speed', color: 'var(--fm-orange)' },
  tactical: { icon: Brain, desc: 'Improve passing, vision, and tactical awareness', color: 'var(--fm-green)' },
  set_pieces: { icon: CircleDot, desc: 'Practice corners, free kicks, and penalties', color: 'var(--fm-yellow)' },
  match_prep: { icon: Crosshair, desc: 'Prepare specifically for the next opponent', color: 'var(--fm-accent)' },
};

const intensityColors: Record<string, string> = {
  recovery: 'var(--fm-green)',
  light: '#86efac',
  normal: 'var(--fm-yellow)',
  intense: 'var(--fm-orange)',
  double: 'var(--fm-red)',
};

const weekDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export default function Training() {
  const [focus, setFocus] = useState('match_prep');
  const [intensity, setIntensity] = useState('normal');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getTraining().then(data => {
      setFocus(data.focus);
      setIntensity(data.intensity);
    }).catch(() => {});
  }, []);

  const handleSave = async () => {
    await api.updateTraining({ focus, intensity });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const intensityIdx = intensities.indexOf(intensity as typeof intensities[number]);

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      <div className="flex items-center gap-3 mb-4">
        <Dumbbell size={20} className="text-[var(--fm-accent)]" />
        <h1 className="text-2xl font-bold tracking-tight">Training</h1>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Focus selection */}
        <div className="card">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-3">Training Focus</h3>
          <div className="space-y-2">
            {focusTypes.map(f => {
              const meta = focusMeta[f];
              const Icon = meta.icon;
              const isActive = focus === f;
              return (
                <button
                  key={f}
                  onClick={() => setFocus(f)}
                  className={`w-full text-left p-3 rounded-lg border transition-all flex items-start gap-3 ${
                    isActive
                      ? 'border-[var(--fm-accent)] bg-[var(--fm-accent)]/8'
                      : 'border-[var(--fm-border)] hover:border-[var(--fm-text-muted)] hover:bg-[var(--fm-surface2)]'
                  }`}
                >
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
                    style={{ backgroundColor: `color-mix(in srgb, ${meta.color} 15%, transparent)` }}
                  >
                    <Icon size={14} style={{ color: meta.color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-medium capitalize text-sm">{f.replace('_', ' ')}</p>
                      {isActive && <Check size={14} className="text-[var(--fm-accent)]" />}
                    </div>
                    <p className="text-xs text-[var(--fm-text-muted)] mt-0.5 leading-relaxed">{meta.desc}</p>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-4">
          {/* Intensity */}
          <div className="card">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-3">Intensity</h3>

            {/* Visual gradient scale */}
            <div className="mb-3">
              <div className="flex gap-1 mb-2">
                {intensities.map((v, i) => (
                  <button
                    key={v}
                    onClick={() => setIntensity(v)}
                    className="flex-1 h-3 rounded-sm transition-all"
                    style={{
                      backgroundColor: i <= intensityIdx ? intensityColors[v] : 'var(--fm-surface2)',
                      opacity: i <= intensityIdx ? 1 : 0.3,
                    }}
                  />
                ))}
              </div>
              <div className="flex justify-between text-[10px] text-[var(--fm-text-muted)]">
                <span>Recovery</span>
                <span>Maximum</span>
              </div>
            </div>

            {/* Intensity buttons */}
            <div className="flex gap-1.5">
              {intensities.map(i => (
                <button
                  key={i}
                  onClick={() => setIntensity(i)}
                  className={`flex-1 py-2 rounded-lg text-xs font-semibold capitalize transition-all ${
                    intensity === i
                      ? 'text-white shadow-lg'
                      : 'bg-[var(--fm-surface2)] text-[var(--fm-text-muted)] hover:text-[var(--fm-text)]'
                  }`}
                  style={intensity === i ? { backgroundColor: intensityColors[i] } : {}}
                >
                  {i}
                </button>
              ))}
            </div>

            <p className="text-xs text-[var(--fm-text-muted)] mt-3 leading-relaxed">
              {intensity === 'recovery' && 'Minimal physical load. Players recover fitness and reduce injury risk.'}
              {intensity === 'light' && 'Low intensity. Players recover while maintaining form.'}
              {intensity === 'normal' && 'Standard training. Balanced improvement and fitness cost.'}
              {intensity === 'intense' && 'High intensity. Faster improvement but higher injury risk.'}
              {intensity === 'double' && 'Maximum intensity. Significant injury risk and morale impact.'}
            </p>
          </div>

          {/* Weekly Schedule Preview */}
          <div className="card">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-3">Weekly Schedule</h3>
            <div className="grid grid-cols-6 gap-1.5">
              {weekDays.map((day, i) => {
                const isMatchDay = day === 'Sat';
                const isRest = day === 'Mon' && intensity !== 'double';
                const meta = focusMeta[focus];
                return (
                  <div
                    key={day}
                    className={`p-2 rounded-lg text-center ${
                      isMatchDay
                        ? 'bg-[var(--fm-accent)]/10 border border-[var(--fm-accent)]/20'
                        : isRest
                        ? 'bg-[var(--fm-surface2)]'
                        : 'bg-[var(--fm-surface2)]'
                    }`}
                  >
                    <p className="text-[10px] text-[var(--fm-text-muted)] font-semibold mb-1">{day}</p>
                    {isMatchDay ? (
                      <p className="text-[9px] text-[var(--fm-accent)] font-semibold">MATCH</p>
                    ) : isRest ? (
                      <p className="text-[9px] text-[var(--fm-green)] font-semibold">REST</p>
                    ) : (
                      <div
                        className="w-3 h-3 rounded-full mx-auto"
                        style={{ backgroundColor: meta.color, opacity: 0.7 + (intensityIdx * 0.075) }}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Workload Warning */}
          <div className={`card border-l-[3px] ${
            intensity === 'double' ? 'border-l-[var(--fm-red)]' :
            intensity === 'intense' ? 'border-l-[var(--fm-orange)]' :
            'border-l-[var(--fm-green)]'
          }`}>
            <div className="flex items-start gap-2">
              {(intensity === 'double' || intensity === 'intense') ? (
                <AlertTriangle size={16} className={intensity === 'double' ? 'text-[var(--fm-red)]' : 'text-[var(--fm-orange)]'} />
              ) : (
                <Check size={16} className="text-[var(--fm-green)]" />
              )}
              <div>
                <p className={`text-sm font-semibold ${
                  intensity === 'double' ? 'text-[var(--fm-red)]' :
                  intensity === 'intense' ? 'text-[var(--fm-orange)]' :
                  'text-[var(--fm-green)]'
                }`}>
                  {intensity === 'double' && 'HIGH RISK'}
                  {intensity === 'intense' && 'MODERATE RISK'}
                  {intensity === 'normal' && 'LOW RISK'}
                  {intensity === 'light' && 'MINIMAL RISK'}
                  {intensity === 'recovery' && 'NO RISK'}
                </p>
                <p className="text-xs text-[var(--fm-text-muted)] mt-0.5">
                  {intensity === 'double' && 'Overtraining may cause injuries, fatigue, and morale drops.'}
                  {intensity === 'intense' && 'Some players may pick up knocks during training.'}
                  {intensity === 'normal' && 'Safe training level for sustained improvement.'}
                  {intensity === 'light' && 'Recovery-focused with light skill work.'}
                  {intensity === 'recovery' && 'Full recovery mode. Ideal after congested fixtures.'}
                </p>
              </div>
            </div>
          </div>

          <button
            onClick={handleSave}
            className={`w-full py-3 rounded-lg font-semibold text-sm shadow-lg transition-all ${
              saved
                ? 'bg-[var(--fm-green)] text-white shadow-green-500/20'
                : 'bg-[var(--fm-accent)] text-white hover:brightness-110 shadow-blue-500/20'
            }`}
          >
            {saved ? 'Saved!' : 'Save Training Plan'}
          </button>
        </div>
      </div>
    </motion.div>
  );
}
