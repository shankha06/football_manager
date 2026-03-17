import { create } from 'zustand';
import type {
  ClubInfo, BoardInfo, PlayerDetail, TacticsSetup, MatchResult,
  SeasonState, NewsItem, LeagueStanding, TransferBid, WSMessage,
} from '../types';
import * as api from '../api/client';

// ── Game Slice ──
interface GameSlice {
  seasonState: SeasonState | null;
  club: ClubInfo | null;
  board: BoardInfo | null;
  standings: LeagueStanding[];
  news: NewsItem[];
  newsTotal: number;
  loading: boolean;
  error: string | null;
  // Actions
  fetchSeasonState: () => Promise<void>;
  fetchClub: () => Promise<void>;
  fetchBoard: () => Promise<void>;
  fetchStandings: () => Promise<void>;
  fetchNews: (page?: number) => Promise<void>;
  advanceMatchday: () => Promise<void>;
}

// ── Squad Slice ──
interface SquadSlice {
  players: PlayerDetail[];
  selectedPlayer: PlayerDetail | null;
  loadingSquad: boolean;
  fetchSquad: () => Promise<void>;
  fetchPlayer: (id: number) => Promise<void>;
  clearSelectedPlayer: () => void;
}

// ── Tactics Slice ──
interface TacticsSlice {
  tactics: TacticsSetup | null;
  loadingTactics: boolean;
  fetchTactics: () => Promise<void>;
  updateTactics: (data: Partial<TacticsSetup>) => Promise<void>;
}

// ── Match Slice ──
interface MatchSlice {
  currentMatch: MatchResult | null;
  matchMessages: WSMessage[];
  isMatchLive: boolean;
  simulateMatch: () => Promise<void>;
  setMatchLive: (live: boolean) => void;
  addMatchMessage: (msg: WSMessage) => void;
  clearMatch: () => void;
}

// ── Combined Store ──
type StoreState = GameSlice & SquadSlice & TacticsSlice & MatchSlice;

export const useStore = create<StoreState>((set, get) => ({
  // ── Game state ──
  seasonState: null,
  club: null,
  board: null,
  standings: [],
  news: [],
  newsTotal: 0,
  loading: false,
  error: null,

  fetchSeasonState: async () => {
    try {
      const state = await api.getSeasonState();
      set({ seasonState: state, error: null });
    } catch (e) {
      const msg = (e as { message?: string })?.message ?? '';
      set({ error: msg.includes('Network Error') ? 'Cannot connect to API server. Start it with: uv run python -m fm --api' : 'Failed to fetch season state' });
    }
  },

  fetchClub: async () => {
    try {
      const club = await api.getClub();
      set({ club, error: null });
    } catch (e) {
      const msg = (e as { message?: string })?.message ?? '';
      if (!msg.includes('Network Error')) set({ error: 'Failed to fetch club info' });
    }
  },

  fetchBoard: async () => {
    try {
      const board = await api.getBoard();
      set({ board });
    } catch (e) {
      set({ error: 'Failed to fetch board' });
    }
  },

  fetchStandings: async () => {
    try {
      const standings = await api.getStandings();
      set({ standings });
    } catch (e) {
      set({ error: 'Failed to fetch standings' });
    }
  },

  fetchNews: async (page = 1) => {
    try {
      const { items, total } = await api.getNews(page);
      set({ news: items, newsTotal: total });
    } catch (e) {
      set({ error: 'Failed to fetch news' });
    }
  },

  advanceMatchday: async () => {
    set({ loading: true, error: null });
    try {
      await api.advanceSeason();
      // Refresh all game state after advancing
      await Promise.all([
        get().fetchSeasonState(),
        get().fetchStandings(),
        get().fetchNews(),
        get().fetchClub(),
        get().fetchSquad(),
      ]);
    } catch (e) {
      const msg = (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
        ?? (e as { message?: string })?.message ?? 'Failed to advance matchday';
      set({ error: msg });
    } finally {
      set({ loading: false });
    }
  },

  // ── Squad ──
  players: [],
  selectedPlayer: null,
  loadingSquad: false,

  fetchSquad: async () => {
    set({ loadingSquad: true });
    try {
      const players = await api.getSquad();
      set({ players, loadingSquad: false });
    } catch (e) {
      set({ loadingSquad: false, error: 'Failed to fetch squad' });
    }
  },

  fetchPlayer: async (id: number) => {
    try {
      const player = await api.getPlayer(id);
      set({ selectedPlayer: player });
    } catch (e) {
      set({ error: 'Failed to fetch player' });
    }
  },

  clearSelectedPlayer: () => set({ selectedPlayer: null }),

  // ── Tactics ──
  tactics: null,
  loadingTactics: false,

  fetchTactics: async () => {
    set({ loadingTactics: true });
    try {
      const tactics = await api.getTactics();
      set({ tactics, loadingTactics: false });
    } catch (e) {
      set({ loadingTactics: false, error: 'Failed to fetch tactics' });
    }
  },

  updateTactics: async (data: Partial<TacticsSetup>) => {
    try {
      const tactics = await api.updateTactics(data);
      set({ tactics });
    } catch (e) {
      set({ error: 'Failed to update tactics' });
    }
  },

  // ── Match ──
  currentMatch: null,
  matchMessages: [],
  isMatchLive: false,

  simulateMatch: async () => {
    set({ loading: true });
    try {
      const result = await api.simulateMatch();
      set({ currentMatch: result, loading: false });
    } catch (e) {
      set({ loading: false, error: 'Failed to simulate match' });
    }
  },

  setMatchLive: (live: boolean) => set({ isMatchLive: live }),
  addMatchMessage: (msg: WSMessage) =>
    set(state => ({ matchMessages: [...state.matchMessages, msg] })),
  clearMatch: () => set({ currentMatch: null, matchMessages: [], isMatchLive: false }),
}));
