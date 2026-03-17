import axios from 'axios';
import type {
  ClubInfo, BoardInfo, PlayerDetail, TacticsSetup, MatchResult,
  SeasonState, NewsItem, TransferTarget, TransferBid, SaveGame,
  LeagueStanding, FormDataPoint, XGDataPoint, PlayerBrief,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

// ── Saves ──
export const listSaves = () => api.get<SaveGame[]>('/saves').then(r => r.data);
export const createSave = (data: { club_id: number; save_name: string; manager_name: string }) =>
  api.post<SaveGame>('/saves', data).then(r => r.data);
export const deleteSave = (id: number) => api.delete(`/saves/${id}`);
export const loadSave = (id: number) => api.get<SaveGame>(`/saves/${id}`).then(r => r.data);

// ── New Game Setup ──
export interface LeagueWithClubs {
  id: number; name: string; country: string; tier: number;
  clubs: { id: number; name: string; reputation: number; budget: number; squad_size: number }[];
}
export interface IngestResult { leagues: number; clubs: number; players: number; fixtures: number; }
export const runIngestion = () => api.post<IngestResult>('/saves/ingest', {}, { timeout: 300000 }).then(r => r.data);
export const getLeaguesWithClubs = () => api.get<LeagueWithClubs[]>('/saves/leagues').then(r => r.data);

// ── Club ──
export const getClub = () => api.get<ClubInfo>('/club').then(r => r.data);
export const getBoard = () => api.get<BoardInfo>('/club/board').then(r => r.data);

// ── Squad ──
export const getSquad = () => api.get<PlayerDetail[]>('/squad').then(r => r.data);
export const getPlayer = (id: number) => api.get<PlayerDetail>(`/squad/${id}`).then(r => r.data);
export const comparePlayers = (id1: number, id2: number) =>
  api.get<{ player1: PlayerDetail; player2: PlayerDetail }>(`/squad/${id1}/compare/${id2}`).then(r => r.data);

// ── Tactics ──
export const getTactics = () => api.get<TacticsSetup>('/tactics').then(r => r.data);
export const updateTactics = (data: Partial<TacticsSetup>) =>
  api.put<TacticsSetup>('/tactics', data).then(r => r.data);
export const getTacticalEffectiveness = (opponentId: number) =>
  api.get<{ score: number; breakdown: Record<string, number> }>(`/tactics/effectiveness/${opponentId}`).then(r => r.data);

// ── Match ──
export interface NextFixture {
  fixture_id: number; matchday: number; home_club: string; away_club: string;
  home_club_id: number; away_club_id: number; is_home: boolean;
}
export const getNextFixture = () => api.get<NextFixture>('/match/next').then(r => r.data);
export const simulateMatch = () => api.post<MatchResult>('/match/simulate').then(r => r.data);
export const getMatchAnalytics = (fixtureId: number) =>
  api.get<{ xg_timeline: XGDataPoint[]; events: MatchResult['events'] }>(`/match/${fixtureId}/analytics`).then(r => r.data);

// ── Training ──
export const getTraining = () => api.get<{ focus: string; intensity: string }>('/training').then(r => r.data);
export const updateTraining = (data: { focus: string; intensity: string }) =>
  api.put('/training', data).then(r => r.data);

// ── Transfers ──
export const searchMarket = (filters?: { position?: string; max_age?: number; max_value?: number }) =>
  api.get<TransferTarget[]>('/transfers/market', { params: filters }).then(r => r.data);
export const placeBid = (data: { player_id: number; bid_amount: number; offered_wage: number; contract_years: number }) =>
  api.post<TransferBid>('/transfers/bid', data).then(r => r.data);
export const getActiveBids = () => api.get<TransferBid[]>('/transfers/bids').then(r => r.data);

// ── Season ──
export const advanceSeason = () => api.post<{ matchday: number; results: MatchResult[] }>('/season/advance').then(r => r.data);
export const getSeasonState = () => api.get<SeasonState>('/season/state').then(r => r.data);
export const getStandings = () => api.get<LeagueStanding[]>('/season/standings').then(r => r.data);

// ── Analytics ──
export const getXGData = () => api.get<XGDataPoint[]>('/analytics/xg').then(r => r.data);
export const getFormData = (playerId?: number) =>
  api.get<FormDataPoint[]>('/analytics/form', { params: { player_id: playerId } }).then(r => r.data);

// ── News ──
export const getNews = (page = 1, perPage = 20) =>
  api.get<{ items: NewsItem[]; total: number }>('/news', { params: { page, per_page: perPage } }).then(r => r.data);
export const markNewsRead = (id: number) => api.post(`/news/${id}/read`);

// ── Scouting ──
export const getScoutAssignments = () => api.get('/scouting/assignments').then(r => r.data);
export const createScoutAssignment = (data: { scout_id: number; player_id?: number; region?: string }) =>
  api.post('/scouting/assignments', data).then(r => r.data);

export default api;
