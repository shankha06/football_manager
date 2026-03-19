import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, Play, Loader2, ArrowLeft, Search, Star, ChevronDown, ChevronRight } from 'lucide-react';
import type { SaveGame } from '../types';
import * as api from '../api/client';
import type { LeagueWithClubs, IngestResult } from '../api/client';
import ClubBadge from '../components/common/ClubBadge';

type Step = 'menu' | 'setup' | 'loading' | 'select_club' | 'confirm';

export default function SaveManager() {
  const [saves, setSaves] = useState<SaveGame[]>([]);
  const [step, setStep] = useState<Step>('menu');
  const [saveName, setSaveName] = useState('');
  const [managerName, setManagerName] = useState('');
  const [error, setError] = useState('');
  const [ingestResult, setIngestResult] = useState<IngestResult | null>(null);

  // Club selection state
  const [leagues, setLeagues] = useState<LeagueWithClubs[]>([]);
  const [expandedLeague, setExpandedLeague] = useState<number | null>(null);
  const [selectedClub, setSelectedClub] = useState<LeagueWithClubs['clubs'][0] | null>(null);
  const [selectedLeagueName, setSelectedLeagueName] = useState('');
  const [search, setSearch] = useState('');
  const [tierFilter, setTierFilter] = useState<number>(0);

  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.listSaves().then(setSaves).catch(() => { });
  }, []);

  // ── Step: Loading data ──
  const handleStartNewGame = () => {
    if (!saveName.trim()) { setError('Enter a save name'); return; }
    setError('');
    setStep('loading');
    api.runIngestion()
      .then((result) => {
        setIngestResult(result);
        return api.getLeaguesWithClubs();
      })
      .then((data) => {
        setLeagues(data);
        if (data.length > 0) setExpandedLeague(data[0].id);
        setStep('select_club');
      })
      .catch((e) => {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Ingestion failed';
        setError(msg);
        setStep('setup');
      });
  };

  // ── Step: Create save with selected club ──
  const handleConfirm = async () => {
    if (!selectedClub) return;
    setCreating(true);
    setError('');
    try {
      await api.createSave({
        club_id: selectedClub.id,
        save_name: saveName.trim(),
        manager_name: managerName.trim() || 'Player',
      });
      navigate('/dashboard');
    } catch (e) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to create game';
      setError(msg);
      setCreating(false);
    }
  };

  // ── Filtered leagues/clubs ──
  const filteredLeagues = useMemo(() => {
    let result = leagues;
    if (tierFilter > 0) {
      result = result.filter(l => l.tier === tierFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result
        .map(l => ({
          ...l,
          clubs: l.clubs.filter(c => c.name.toLowerCase().includes(q)),
        }))
        .filter(l => l.clubs.length > 0);
    }
    return result;
  }, [leagues, tierFilter, search]);

  const tiers = [...new Set(leagues.map(l => l.tier))].sort();

  const handleLoad = (save: SaveGame) => {
    api.loadSave(save.id).catch(() => { });
    navigate('/dashboard');
  };

  const handleDelete = async (id: number) => {
    await api.deleteSave(id);
    setSaves(saves.filter(s => s.id !== id));
  };

  const starRating = (rep: number) => {
    const count = Math.min(Math.ceil(rep / 20), 5);
    return Array.from({ length: 5 }, (_, i) => (
      <Star key={i} size={12} className={i < count ? 'fill-yellow-400 text-yellow-400' : 'text-[var(--fm-border)]'} />
    ));
  };

  // ── RENDER ──

  // Step: Main menu (list saves or new game)
  if (step === 'menu') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--fm-bg)]">
        <div className="w-full max-w-lg p-8">
          <h1 className="text-3xl font-bold text-[var(--fm-accent)] mb-2">Football Manager v3</h1>
          <p className="text-[var(--fm-text-muted)] mb-8">Select a save or start a new game</p>

          {saves.length > 0 && (
            <div className="mb-6 space-y-2">
              {saves.map(save => (
                <div key={save.id} className="flex items-center justify-between p-4 bg-[var(--fm-surface)] rounded-lg border border-[var(--fm-border)]">
                  <div>
                    <p className="font-medium">{save.save_name}</p>
                    <p className="text-sm text-[var(--fm-text-muted)]">{save.club_name} &mdash; Season {save.season}, MD {save.matchday}</p>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => handleLoad(save)} className="p-2 rounded bg-[var(--fm-accent)]/20 text-[var(--fm-accent)] hover:bg-[var(--fm-accent)]/30">
                      <Play size={16} />
                    </button>
                    <button onClick={() => handleDelete(save.id)} className="p-2 rounded bg-[var(--fm-red)]/20 text-[var(--fm-red)] hover:bg-[var(--fm-red)]/30">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <button
            onClick={() => setStep('setup')}
            className="w-full p-4 rounded-lg border-2 border-dashed border-[var(--fm-border)] text-[var(--fm-text-muted)] hover:border-[var(--fm-accent)] hover:text-[var(--fm-accent)] transition-colors flex items-center justify-center gap-2"
          >
            <Plus size={20} /> New Game
          </button>
        </div>
      </div>
    );
  }

  // Step: Enter save name + manager name
  if (step === 'setup') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--fm-bg)]">
        <div className="w-full max-w-md p-8">
          <button onClick={() => { setStep('menu'); setError(''); }} className="flex items-center gap-1 text-[var(--fm-accent)] mb-6 hover:underline text-sm">
            <ArrowLeft size={16} /> Back
          </button>
          <h1 className="text-2xl font-bold mb-6">New Game Setup</h1>

          {error && (
            <div className="p-3 rounded bg-[var(--fm-red)]/10 border border-[var(--fm-red)]/30 text-[var(--fm-red)] text-sm mb-4">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="text-sm text-[var(--fm-text-muted)] block mb-1">Save Name</label>
              <input type="text" placeholder="My Career" value={saveName} onChange={e => setSaveName(e.target.value)}
                className="w-full p-3 rounded bg-[var(--fm-surface)] border border-[var(--fm-border)] text-[var(--fm-text)]" autoFocus />
            </div>
            <div>
              <label className="text-sm text-[var(--fm-text-muted)] block mb-1">Manager Name</label>
              <input type="text" placeholder="Player" value={managerName} onChange={e => setManagerName(e.target.value)}
                className="w-full p-3 rounded bg-[var(--fm-surface)] border border-[var(--fm-border)] text-[var(--fm-text)]" />
            </div>
            <button onClick={handleStartNewGame}
              className="w-full p-3 rounded bg-[var(--fm-accent)] text-white font-medium hover:opacity-90">
              Continue &rarr;
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Step: Loading data
  if (step === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--fm-bg)]">
        <div className="text-center p-8">
          <Loader2 size={48} className="animate-spin text-[var(--fm-accent)] mx-auto mb-4" />
          <h2 className="text-xl font-bold mb-2">Setting Up World</h2>
          <p className="text-[var(--fm-text-muted)]">Loading player data, creating leagues and fixtures...</p>
          <p className="text-xs text-[var(--fm-text-muted)] mt-2">This may take up to a minute on first run.</p>
        </div>
      </div>
    );
  }

  // Step: Club selection (the main one)
  if (step === 'select_club') {
    return (
      <div className="min-h-screen bg-[var(--fm-bg)] p-6">
        <div className="max-w-5xl mx-auto">
          <button onClick={() => setStep('setup')} className="flex items-center gap-1 text-[var(--fm-accent)] mb-4 hover:underline text-sm">
            <ArrowLeft size={16} /> Back
          </button>

          <h1 className="text-2xl font-bold mb-1">Select Your Club</h1>
          {ingestResult && (
            <p className="text-sm text-[var(--fm-text-muted)] mb-4">
              {ingestResult.players.toLocaleString()} players, {ingestResult.clubs} clubs, {ingestResult.leagues} leagues loaded
            </p>
          )}

          {/* Filters */}
          <div className="flex gap-3 mb-4">
            <div className="relative flex-1 max-w-xs">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--fm-text-muted)]" />
              <input type="text" placeholder="Search clubs..." value={search} onChange={e => setSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded bg-[var(--fm-surface)] border border-[var(--fm-border)] text-sm" />
            </div>
            <select value={tierFilter} onChange={e => setTierFilter(Number(e.target.value))}
              className="px-3 py-2 rounded bg-[var(--fm-surface)] border border-[var(--fm-border)] text-sm">
              <option value={0}>All Tiers</option>
              {tiers.map(t => <option key={t} value={t}>Tier {t}</option>)}
            </select>
          </div>

          {/* League accordion with clubs */}
          <div className="space-y-1">
            {filteredLeagues.map(league => {
              const isExpanded = expandedLeague === league.id;
              return (
                <div key={league.id} className="bg-[var(--fm-surface)] rounded-lg border border-[var(--fm-border)] overflow-hidden">
                  {/* League header */}
                  <button
                    onClick={() => setExpandedLeague(isExpanded ? null : league.id)}
                    className="w-full flex items-center justify-between px-4 py-3 hover:bg-[var(--fm-surface2)] transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      {isExpanded ? <ChevronDown size={16} className="text-[var(--fm-accent)]" /> : <ChevronRight size={16} className="text-[var(--fm-text-muted)]" />}
                      <span className="font-medium">{league.name}</span>
                      <span className="text-xs text-[var(--fm-text-muted)]">{league.country}</span>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--fm-surface2)] text-[var(--fm-text-muted)]">Tier {league.tier}</span>
                    </div>
                    <span className="text-xs text-[var(--fm-text-muted)]">{league.clubs.length} clubs</span>
                  </button>

                  {/* Club rows */}
                  {isExpanded && (
                    <div className="border-t border-[var(--fm-border)]">
                      <table className="w-full text-sm">
                        <thead className="bg-[var(--fm-surface2)] text-xs text-[var(--fm-text-muted)] uppercase">
                          <tr>
                            <th className="px-4 py-2 text-left">Club</th>
                            <th className="px-4 py-2 text-center">Reputation</th>
                            <th className="px-4 py-2 text-right">Budget</th>
                            <th className="px-4 py-2 text-center">Squad</th>
                          </tr>
                        </thead>
                        <tbody>
                          {league.clubs.map(club => {
                            const isSelected = selectedClub?.id === club.id;
                            return (
                              <tr
                                key={club.id}
                                onClick={() => { setSelectedClub(club); setSelectedLeagueName(league.name); }}
                                className={`cursor-pointer border-t border-[var(--fm-border)] transition-colors ${isSelected
                                    ? 'bg-[var(--fm-accent)]/15 border-l-2 border-l-[var(--fm-accent)]'
                                    : 'hover:bg-[var(--fm-surface2)]'
                                  }`}
                              >
                                <td className="px-4 py-2.5 font-medium">
                                  <div className="flex items-center gap-2">
                                    <ClubBadge clubId={club.id} name={club.name} size={24} />
                                    <span>{club.name}</span>
                                  </div>
                                </td>
                                <td className="px-4 py-2.5">
                                  <div className="flex items-center justify-center gap-0.5">{starRating(club.reputation)}</div>
                                </td>
                                <td className="px-4 py-2.5 text-right text-[var(--fm-green)]">
                                  {club.budget >= 1 ? `\u20AC${club.budget.toFixed(1)}M` : `\u20AC${(club.budget * 1000).toFixed(0)}K`}
                                </td>
                                <td className="px-4 py-2.5 text-center text-[var(--fm-text-muted)]">{club.squad_size}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Bottom bar: selected club + confirm */}
          {selectedClub && (
            <div className="fixed bottom-0 left-0 right-0 bg-[var(--fm-surface)] border-t border-[var(--fm-border)] px-6 py-4">
              <div className="max-w-5xl mx-auto flex items-center justify-between">
                <div>
                  <p className="font-bold text-lg">{selectedClub.name}</p>
                  <p className="text-sm text-[var(--fm-text-muted)]">
                    {selectedLeagueName} &mdash; Budget: {selectedClub.budget >= 1 ? `\u20AC${selectedClub.budget.toFixed(1)}M` : `\u20AC${(selectedClub.budget * 1000).toFixed(0)}K`} &mdash; Squad: {selectedClub.squad_size} players
                  </p>
                </div>
                <button
                  onClick={handleConfirm}
                  disabled={creating}
                  className="px-6 py-3 bg-[var(--fm-accent)] text-white rounded-lg font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-2"
                >
                  {creating ? <><Loader2 size={16} className="animate-spin" /> Creating...</> : <><Play size={16} /> Start Managing</>}
                </button>
              </div>
              {error && <p className="text-sm text-[var(--fm-red)] mt-2 max-w-5xl mx-auto">{error}</p>}
            </div>
          )}
        </div>
      </div>
    );
  }

  return null;
}
