// ── Core types matching backend Pydantic schemas ──

export interface PlayerBrief {
  id: number;
  name: string;
  position: string;
  overall: number;
  age: number;
  nationality?: string;
}

export interface PlayerDetail extends PlayerBrief {
  short_name?: string;
  club_id?: number;
  club_name?: string;
  wage: number;
  market_value: number;
  potential: number;
  fitness: number;
  morale: number;
  form: number;
  goals_season: number;
  assists_season: number;
  minutes_season: number;
  injured_weeks: number;
  suspended_matches: number;
  squad_role: string;
  trust_in_manager: number;
  fan_favorite: boolean;
  // Attributes
  pace: number;
  shooting: number;
  passing: number;
  dribbling: number;
  defending: number;
  physical: number;
  // GK
  gk_diving?: number;
  gk_handling?: number;
  gk_positioning?: number;
  gk_reflexes?: number;
  // Hidden
  consistency: number;
  big_match: number;
  composure: number;
  // Contract
  contract_expiry: number;
  release_clause?: number;
}

export interface ClubInfo {
  id: number;
  name: string;
  short_name?: string;
  league_name: string;
  reputation: number;
  budget: number;
  wage_budget: number;
  total_wages: number;
  stadium_capacity: number;
  stadium_name?: string;
  team_spirit: number;
  primary_color: string;
  secondary_color: string;
}

export interface BoardInfo {
  board_confidence: number;
  fan_happiness: number;
  min_league_position: number;
  max_league_position: number;
  patience: number;
  warnings_issued: number;
  ultimatum_active: boolean;
  transfer_embargo: boolean;
  style_expectation: string;
}

export interface TacticsSetup {
  formation: string;
  mentality: string;
  tempo: string;
  pressing: string;
  passing_style: string;
  width: string;
  defensive_line: string;
  offside_trap: boolean;
  counter_attack: boolean;
  play_out_from_back: boolean;
  time_wasting: string;
  match_plan_winning: string;
  match_plan_losing: string;
  match_plan_drawing: string;
  captain_id?: number;
  penalty_taker_id?: number;
  corner_taker_id?: number;
  free_kick_taker_id?: number;
}

export interface MatchEvent {
  minute: number;
  event_type: string;
  description?: string;
  player_name?: string;
  assist_player_name?: string;
  team_side?: string;
  // Convenience aliases used in UI
  type?: string;
  text?: string;
}

export interface MatchResult {
  fixture_id: number;
  home_club: string;
  away_club: string;
  home_club_id: number;
  away_club_id: number;
  xg_timeline?: XGDataPoint[];
  home_goals: number;
  away_goals: number;
  home_xg?: number | null;
  away_xg?: number | null;
  home_possession?: number | null;
  away_possession?: number | null;
  home_shots?: number | null;
  home_shots_on_target?: number | null;
  away_shots?: number | null;
  away_shots_on_target?: number | null;
  attendance?: number | null;
  weather?: string | null;
  motm_player_name?: string | null;
  // Passing
  home_passes?: number | null;
  home_pass_accuracy?: number | null;
  away_passes?: number | null;
  away_pass_accuracy?: number | null;
  // Defense
  home_tackles?: number | null;
  away_tackles?: number | null;
  home_interceptions?: number | null;
  away_interceptions?: number | null;
  home_clearances?: number | null;
  away_clearances?: number | null;
  // Set pieces
  home_corners?: number | null;
  away_corners?: number | null;
  home_fouls?: number | null;
  away_fouls?: number | null;
  home_offsides?: number | null;
  away_offsides?: number | null;
  // Discipline
  home_yellow_cards?: number | null;
  away_yellow_cards?: number | null;
  home_red_cards?: number | null;
  away_red_cards?: number | null;
  // GK
  home_saves?: number | null;
  away_saves?: number | null;
  // Advanced
  home_crosses?: number | null;
  away_crosses?: number | null;
  home_dribbles_completed?: number | null;
  away_dribbles_completed?: number | null;
  home_aerials_won?: number | null;
  away_aerials_won?: number | null;
  home_big_chances?: number | null;
  away_big_chances?: number | null;
  home_key_passes?: number | null;
  away_key_passes?: number | null;
  events: MatchEvent[];
}

export interface LeagueStanding {
  club_id: number;
  club_name: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
  form: string;
}

export interface SeasonState {
  season: number;
  current_matchday: number;
  total_matchdays: number;
  phase: string;
  human_club_id: number;
}

export interface NewsItem {
  id: number;
  headline: string;
  body?: string;
  category: string;
  matchday?: number;
  is_read: boolean;
}

export interface TransferTarget {
  player: PlayerBrief;
  club_name: string;
  market_value: number;
  wage: number;
  contract_expiry: number;
  asking_price: number;
}

export interface TransferBid {
  id: number;
  player_name: string;
  bid_amount: number;
  status: string;
  offered_wage: number;
}

export interface SaveGame {
  id: number;
  save_name: string;
  club_name: string;
  season: number;
  matchday: number;
  last_played?: string;
}

export interface FormDataPoint {
  matchday: number;
  rating: number;
}

export interface XGDataPoint {
  matchday: number;
  xg_for: number;
  xg_against: number;
  goals_for: number;
  goals_against: number;
}

// Live match WebSocket messages
export interface WSMessage {
  type: 'commentary' | 'goal' | 'stats_update' | 'match_end' | 'card' | 'substitution' | 'match_start';
  minute?: number;
  text?: string;
  data?: Record<string, unknown>;
}
