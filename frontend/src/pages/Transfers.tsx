import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, DollarSign, X, ArrowRightLeft,
} from 'lucide-react';
import type { TransferTarget, TransferBid } from '../types';
import * as api from '../api/client';

const posColors: Record<string, { bg: string; text: string }> = {
  GK: { bg: 'bg-yellow-500/15', text: 'text-yellow-400' },
  CB: { bg: 'bg-blue-500/15', text: 'text-blue-400' },
  LB: { bg: 'bg-blue-500/15', text: 'text-blue-400' },
  RB: { bg: 'bg-blue-500/15', text: 'text-blue-400' },
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

function getInitials(name: string): string {
  const parts = name.split(' ');
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

export default function Transfers() {
  const [results, setResults] = useState<TransferTarget[]>([]);
  const [bids, setBids] = useState<TransferBid[]>([]);
  const [posFilter, setPosFilter] = useState('');
  const [maxAge, setMaxAge] = useState(35);
  const [maxValue, setMaxValue] = useState(200);
  const [searching, setSearching] = useState(false);
  const [bidModal, setBidModal] = useState<TransferTarget | null>(null);
  const [bidAmount, setBidAmount] = useState(0);
  const [bidWage, setBidWage] = useState(0);

  useEffect(() => {
    api.getActiveBids().then(setBids).catch(() => {});
  }, []);

  const handleSearch = async () => {
    setSearching(true);
    try {
      const data = await api.searchMarket({
        position: posFilter || undefined,
        max_age: maxAge,
        max_value: maxValue,
      });
      setResults(data);
    } finally {
      setSearching(false);
    }
  };

  const handleBid = async () => {
    if (!bidModal) return;
    try {
      const bid = await api.placeBid({
        player_id: bidModal.player.id,
        bid_amount: bidAmount,
        offered_wage: bidWage,
        contract_years: 3,
      });
      setBids([...bids, bid]);
      setBidModal(null);
    } catch {
      // error
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      <div className="flex items-center gap-3 mb-4">
        <ArrowRightLeft size={20} className="text-[var(--fm-accent)]" />
        <h1 className="text-2xl font-bold tracking-tight">Transfer Market</h1>
      </div>

      {/* Search panel */}
      <div className="card mb-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-3">Search Filters</h3>
        <div className="flex gap-3 items-end">
          <div className="flex-1 max-w-[140px]">
            <label className="text-[10px] text-[var(--fm-text-muted)] block mb-1">Position</label>
            <select value={posFilter} onChange={e => setPosFilter(e.target.value)}
              className="block w-full p-2 rounded-lg bg-[var(--fm-surface2)] border border-[var(--fm-border)] text-sm">
              <option value="">Any</option>
              {['GK','CB','LB','RB','CDM','CM','CAM','LW','RW','ST'].map(p =>
                <option key={p} value={p}>{p}</option>
              )}
            </select>
          </div>
          <div className="w-20">
            <label className="text-[10px] text-[var(--fm-text-muted)] block mb-1">Max Age</label>
            <input type="number" value={maxAge} onChange={e => setMaxAge(+e.target.value)}
              className="block w-full p-2 rounded-lg bg-[var(--fm-surface2)] border border-[var(--fm-border)] text-sm" />
          </div>
          <div className="w-28">
            <label className="text-[10px] text-[var(--fm-text-muted)] block mb-1">Max Value (M)</label>
            <input type="number" value={maxValue} onChange={e => setMaxValue(+e.target.value)}
              className="block w-full p-2 rounded-lg bg-[var(--fm-surface2)] border border-[var(--fm-border)] text-sm" />
          </div>
          <button onClick={handleSearch} disabled={searching}
            className="px-5 py-2 bg-[var(--fm-accent)] text-white rounded-lg text-sm font-semibold flex items-center gap-1.5 hover:brightness-110 disabled:opacity-50 shadow-lg shadow-blue-500/15">
            {searching ? (
              <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Search size={14} />
            )}
            {searching ? 'Searching...' : 'Search'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Results as cards */}
        <div className="col-span-2">
          {results.length > 0 ? (
            <div className="grid grid-cols-2 gap-3">
              {results.map((t, i) => {
                const pc = posColors[t.player.position] ?? { bg: 'bg-gray-500/15', text: 'text-gray-400' };
                return (
                  <motion.div
                    key={t.player.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2, delay: i * 0.03 }}
                    className="card card-interactive !p-0 overflow-hidden"
                    onClick={() => { setBidModal(t); setBidAmount(t.asking_price); setBidWage(t.wage * 1.1); }}
                  >
                    <div className="p-3">
                      <div className="flex items-start gap-3">
                        {/* Avatar */}
                        <div className={`w-11 h-11 rounded-lg flex items-center justify-center text-white text-sm font-bold flex-shrink-0 ${ovrColor(t.player.overall)}`}>
                          {getInitials(t.player.name)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-sm truncate">{t.player.name}</p>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${pc.bg} ${pc.text}`}>{t.player.position}</span>
                            <span className="text-[10px] text-[var(--fm-text-muted)]">Age {t.player.age}</span>
                          </div>
                        </div>
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0 ${ovrColor(t.player.overall)}`}>
                          {t.player.overall}
                        </div>
                      </div>
                      <div className="flex items-center justify-between mt-2.5 pt-2 border-t border-[var(--fm-border)]">
                        <div>
                          <p className="text-[10px] text-[var(--fm-text-muted)]">Club</p>
                          <p className="text-xs font-medium">{t.club_name}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-[10px] text-[var(--fm-text-muted)]">Value / Wage</p>
                          <p className="text-xs font-medium">
                            <span className="text-[var(--fm-green)]">{formatMoney(t.market_value)}</span>
                            <span className="text-[var(--fm-text-muted)]"> / </span>
                            <span>{formatMoney(t.wage)}/w</span>
                          </p>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          ) : (
            <div className="card text-center py-12">
              <Search size={32} className="text-[var(--fm-text-muted)] mx-auto mb-3 opacity-40" />
              <p className="text-sm text-[var(--fm-text-muted)]">Search the transfer market to find players</p>
            </div>
          )}
        </div>

        {/* Active Bids */}
        <div className="card">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fm-text-muted)] mb-3 flex items-center gap-1.5">
            <DollarSign size={13} /> Active Bids
          </h3>
          {bids.length > 0 ? (
            <div className="space-y-2">
              {bids.map(b => (
                <div key={b.id} className="p-2.5 rounded-lg bg-[var(--fm-surface2)] border border-[var(--fm-border)]">
                  <p className="font-medium text-sm">{b.player_name}</p>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-xs text-[var(--fm-text-muted)]">{formatMoney(b.bid_amount)}</span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      b.status === 'accepted' ? 'bg-[var(--fm-green)]/15 text-[var(--fm-green)]' :
                      b.status === 'rejected' ? 'bg-[var(--fm-red)]/15 text-[var(--fm-red)]' :
                      'bg-[var(--fm-yellow)]/15 text-[var(--fm-yellow)]'
                    }`}>
                      {b.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-[var(--fm-text-muted)] text-center py-4">No active bids</p>
          )}
        </div>
      </div>

      {/* Bid Modal */}
      <AnimatePresence>
        {bidModal && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/50 z-50"
              onClick={() => setBidModal(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[420px] bg-[var(--fm-surface)] rounded-xl border border-[var(--fm-border)] p-6 z-50 shadow-2xl"
            >
              {/* Player summary */}
              <div className="flex items-start justify-between mb-5">
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-12 rounded-lg flex items-center justify-center text-white font-bold ${ovrColor(bidModal.player.overall)}`}>
                    {bidModal.player.overall}
                  </div>
                  <div>
                    <h3 className="text-lg font-bold">{bidModal.player.name}</h3>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-[var(--fm-text-muted)]">{bidModal.player.position}</span>
                      <span className="text-xs text-[var(--fm-text-muted)]">Age {bidModal.player.age}</span>
                      <span className="text-xs text-[var(--fm-text-muted)]">{bidModal.club_name}</span>
                    </div>
                  </div>
                </div>
                <button onClick={() => setBidModal(null)} className="p-1 rounded hover:bg-[var(--fm-surface2)]">
                  <X size={18} className="text-[var(--fm-text-muted)]" />
                </button>
              </div>

              {/* Asking price info */}
              <div className="flex gap-3 mb-4">
                <div className="flex-1 p-2.5 rounded-lg bg-[var(--fm-surface2)] text-center">
                  <p className="text-[10px] text-[var(--fm-text-muted)]">Asking Price</p>
                  <p className="text-sm font-bold text-[var(--fm-green)]">{formatMoney(bidModal.asking_price)}</p>
                </div>
                <div className="flex-1 p-2.5 rounded-lg bg-[var(--fm-surface2)] text-center">
                  <p className="text-[10px] text-[var(--fm-text-muted)]">Current Wage</p>
                  <p className="text-sm font-bold">{formatMoney(bidModal.wage)}/w</p>
                </div>
              </div>

              {/* Bid inputs */}
              <div className="space-y-3 mb-5">
                <div>
                  <label className="text-xs text-[var(--fm-text-muted)] block mb-1.5">Bid Amount (M)</label>
                  <input type="number" step="0.1" value={bidAmount} onChange={e => setBidAmount(+e.target.value)}
                    className="w-full p-2.5 rounded-lg bg-[var(--fm-surface2)] border border-[var(--fm-border)] text-sm font-semibold" />
                </div>
                <div>
                  <label className="text-xs text-[var(--fm-text-muted)] block mb-1.5">Weekly Wage Offer (M)</label>
                  <input type="number" step="0.01" value={bidWage} onChange={e => setBidWage(+e.target.value)}
                    className="w-full p-2.5 rounded-lg bg-[var(--fm-surface2)] border border-[var(--fm-border)] text-sm font-semibold" />
                </div>
              </div>

              <div className="flex gap-2">
                <button onClick={handleBid}
                  className="flex-1 py-2.5 bg-[var(--fm-accent)] text-white rounded-lg font-semibold text-sm hover:brightness-110 shadow-lg shadow-blue-500/15">
                  Submit Bid
                </button>
                <button onClick={() => setBidModal(null)}
                  className="py-2.5 px-5 border border-[var(--fm-border)] rounded-lg text-sm font-medium hover:bg-[var(--fm-surface2)]">
                  Cancel
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function formatMoney(m: number): string {
  if (m >= 1) return `\u20AC${m.toFixed(1)}M`;
  return `\u20AC${(m * 1000).toFixed(0)}K`;
}
