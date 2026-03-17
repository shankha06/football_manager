import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, BarChart, Bar } from 'recharts';
import { motion } from 'framer-motion';
import { BarChart3, Target, Shield, TrendingUp, Percent } from 'lucide-react';
import type { XGDataPoint, FormDataPoint } from '../types';
import * as api from '../api/client';

export default function Analytics() {
  const [xgData, setXgData] = useState<XGDataPoint[]>([]);
  const [formData, setFormData] = useState<FormDataPoint[]>([]);

  useEffect(() => {
    api.getXGData().then(setXgData).catch(() => {});
    api.getFormData().then(setFormData).catch(() => {});
  }, []);

  // Season overview stats
  const totalGoalsFor = xgData.reduce((s, d) => s + d.goals_for, 0);
  const totalGoalsAgainst = xgData.reduce((s, d) => s + d.goals_against, 0);
  const cleanSheets = xgData.filter(d => d.goals_against === 0).length;
  const totalMatches = xgData.length;
  const totalXgFor = xgData.reduce((s, d) => s + d.xg_for, 0);

  const tooltipStyle = {
    contentStyle: {
      background: 'var(--fm-surface)',
      border: '1px solid var(--fm-border)',
      borderRadius: 10,
      fontSize: 12,
      boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
    },
    labelStyle: { color: 'var(--fm-text)', fontWeight: 600 },
    itemStyle: { color: 'var(--fm-text-muted)' },
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      <div className="flex items-center gap-3 mb-4">
        <BarChart3 size={20} className="text-[var(--fm-accent)]" />
        <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
      </div>

      {/* Season Overview Cards */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        <OverviewCard
          icon={Target}
          label="Goals Scored"
          value={totalGoalsFor}
          sub={`xG: ${totalXgFor.toFixed(1)}`}
          color="var(--fm-green)"
        />
        <OverviewCard
          icon={Shield}
          label="Goals Conceded"
          value={totalGoalsAgainst}
          color="var(--fm-red)"
        />
        <OverviewCard
          icon={TrendingUp}
          label="Clean Sheets"
          value={cleanSheets}
          sub={`${totalMatches > 0 ? ((cleanSheets / totalMatches) * 100).toFixed(0) : 0}%`}
          color="var(--fm-accent)"
        />
        <OverviewCard
          icon={Percent}
          label="Goals/Match"
          value={totalMatches > 0 ? (totalGoalsFor / totalMatches).toFixed(1) : '--'}
          color="var(--fm-yellow)"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* xG Timeline */}
        <div className="card">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-4">
            Expected Goals (xG) Timeline
          </h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={xgData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--fm-border)" strokeOpacity={0.5} />
              <XAxis dataKey="matchday" stroke="var(--fm-text-muted)" fontSize={11} tickLine={false} />
              <YAxis stroke="var(--fm-text-muted)" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fm-text-muted)' }} />
              <Line type="monotone" dataKey="xg_for" name="xG For" stroke="var(--fm-accent)" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="xg_against" name="xG Against" stroke="var(--fm-red)" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="goals_for" name="Goals" stroke="var(--fm-green)" strokeWidth={1.5} strokeDasharray="5 5" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Goals vs xG Bar Chart */}
        <div className="card">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-4">
            Goals vs xG (Last 10)
          </h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={xgData.slice(-10)}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--fm-border)" strokeOpacity={0.5} />
              <XAxis dataKey="matchday" stroke="var(--fm-text-muted)" fontSize={11} tickLine={false} />
              <YAxis stroke="var(--fm-text-muted)" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fm-text-muted)' }} />
              <Bar dataKey="goals_for" name="Goals" fill="var(--fm-green)" radius={[3, 3, 0, 0]} />
              <Bar dataKey="xg_for" name="xG" fill="var(--fm-accent)" radius={[3, 3, 0, 0]} opacity={0.5} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Form Graph */}
        <div className="col-span-2 card">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-4">
            Team Performance Rating Over Time
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={formData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--fm-border)" strokeOpacity={0.5} />
              <XAxis dataKey="matchday" stroke="var(--fm-text-muted)" fontSize={11} tickLine={false} />
              <YAxis domain={[4, 10]} stroke="var(--fm-text-muted)" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip {...tooltipStyle} />
              <Line
                type="monotone"
                dataKey="rating"
                name="Avg Rating"
                stroke="var(--fm-yellow)"
                strokeWidth={2.5}
                dot={{ r: 3, fill: 'var(--fm-yellow)', strokeWidth: 0 }}
                activeDot={{ r: 5, stroke: 'var(--fm-yellow)', strokeWidth: 2 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </motion.div>
  );
}

function OverviewCard({ icon: Icon, label, value, sub, color }: {
  icon: React.ElementType; label: string; value: number | string; sub?: string; color: string;
}) {
  return (
    <div className="card flex items-center gap-3 !py-3">
      <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)` }}>
        <Icon size={18} style={{ color }} />
      </div>
      <div>
        <p className="text-xl font-bold tabular-nums">{value}</p>
        <p className="text-[10px] text-[var(--fm-text-muted)]">{label}</p>
        {sub && <p className="text-[10px] text-[var(--fm-text-muted)]">{sub}</p>}
      </div>
    </div>
  );
}
