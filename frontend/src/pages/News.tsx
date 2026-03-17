import { useEffect, useState } from 'react';
import { useStore } from '../store';
import * as api from '../api/client';
import { motion } from 'framer-motion';
import {
  Trophy, Swords, AlertTriangle, DollarSign, Users, Newspaper,
  ChevronLeft, ChevronRight,
} from 'lucide-react';

const categoryIcons: Record<string, React.ElementType> = {
  match: Swords,
  transfer: DollarSign,
  injury: AlertTriangle,
  award: Trophy,
  manager: Users,
  general: Newspaper,
};

const categoryColors: Record<string, { border: string; bg: string; text: string; icon: string }> = {
  match: { border: 'border-l-[var(--fm-accent)]', bg: 'bg-[var(--fm-accent)]/10', text: 'text-[var(--fm-accent)]', icon: 'text-[var(--fm-accent)]' },
  transfer: { border: 'border-l-[var(--fm-green)]', bg: 'bg-[var(--fm-green)]/10', text: 'text-[var(--fm-green)]', icon: 'text-[var(--fm-green)]' },
  injury: { border: 'border-l-[var(--fm-red)]', bg: 'bg-[var(--fm-red)]/10', text: 'text-[var(--fm-red)]', icon: 'text-[var(--fm-red)]' },
  award: { border: 'border-l-[var(--fm-yellow)]', bg: 'bg-[var(--fm-yellow)]/10', text: 'text-[var(--fm-yellow)]', icon: 'text-[var(--fm-yellow)]' },
  manager: { border: 'border-l-purple-400', bg: 'bg-purple-500/10', text: 'text-purple-400', icon: 'text-purple-400' },
  general: { border: 'border-l-[var(--fm-text-muted)]', bg: 'bg-[var(--fm-surface2)]', text: 'text-[var(--fm-text-muted)]', icon: 'text-[var(--fm-text-muted)]' },
};

function getRelativeTime(matchday?: number, currentMatchday?: number): string {
  if (!matchday || !currentMatchday) return '';
  const diff = currentMatchday - matchday;
  if (diff === 0) return 'This matchday';
  if (diff === 1) return '1 matchday ago';
  return `${diff} matchdays ago`;
}

export default function News() {
  const { news, newsTotal, fetchNews, seasonState } = useStore();
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => { fetchNews(page); }, [page]);

  const handleExpand = async (id: number) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    const item = news.find(n => n.id === id);
    if (item && !item.is_read) {
      await api.markNewsRead(id);
      fetchNews(page);
    }
  };

  const totalPages = Math.ceil(newsTotal / 20);

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      <div className="flex items-center gap-3 mb-4">
        <Newspaper size={20} className="text-[var(--fm-accent)]" />
        <h1 className="text-2xl font-bold tracking-tight">News</h1>
        <span className="text-xs text-[var(--fm-text-muted)] ml-2">
          {newsTotal} article{newsTotal !== 1 ? 's' : ''}
        </span>
      </div>

      <div className="space-y-2">
        {news.map((n, i) => {
          const Icon = categoryIcons[n.category] ?? Newspaper;
          const colors = categoryColors[n.category] ?? categoryColors.general;
          const relative = getRelativeTime(n.matchday, seasonState?.current_matchday);

          return (
            <motion.div
              key={n.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: i * 0.03 }}
            >
              <div
                onClick={() => handleExpand(n.id)}
                className={`card cursor-pointer border-l-[3px] transition-all hover:border-[var(--fm-accent)] ${colors.border} ${
                  !n.is_read ? 'unread-glow' : ''
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${colors.bg}`}>
                    <Icon size={14} className={colors.icon} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4">
                      <p className={`font-medium text-sm leading-snug ${!n.is_read ? 'text-[var(--fm-text)]' : 'text-[var(--fm-text-muted)]'}`}>
                        {n.headline}
                      </p>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {!n.is_read && (
                          <div className="w-1.5 h-1.5 rounded-full bg-[var(--fm-accent)]" />
                        )}
                        <span className="text-[10px] text-[var(--fm-text-muted)] whitespace-nowrap">
                          {relative || (n.matchday ? `MD ${n.matchday}` : '')}
                        </span>
                      </div>
                    </div>
                    {expandedId === n.id && n.body && (
                      <motion.p
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        className="text-sm text-[var(--fm-text-muted)] mt-2 whitespace-pre-line leading-relaxed"
                      >
                        {n.body}
                      </motion.p>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          );
        })}
        {news.length === 0 && (
          <div className="card text-center py-12">
            <Newspaper size={32} className="text-[var(--fm-text-muted)] mx-auto mb-3 opacity-40" />
            <p className="text-sm text-[var(--fm-text-muted)]">No news yet</p>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4">
          <button
            disabled={page <= 1}
            onClick={() => setPage(p => p - 1)}
            className="p-2 rounded-lg bg-[var(--fm-surface)] border border-[var(--fm-border)] disabled:opacity-30 hover:bg-[var(--fm-surface2)]"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="text-sm text-[var(--fm-text-muted)] tabular-nums">
            Page {page} of {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(p => p + 1)}
            className="p-2 rounded-lg bg-[var(--fm-surface)] border border-[var(--fm-border)] disabled:opacity-30 hover:bg-[var(--fm-surface2)]"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      )}
    </motion.div>
  );
}
