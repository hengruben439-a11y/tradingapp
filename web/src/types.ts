export type Direction = 'BUY' | 'SELL';
export type SignalStrength = 'very_strong' | 'strong' | 'moderate' | 'watch';
export type Pair = 'XAUUSDB' | 'GBPJPYB';
export type TradingStyle = 'scalping' | 'day_trading' | 'swing_trading' | 'position_trading';
export type UIMode = 'simple' | 'pro' | 'max';

export interface ModuleScore {
  name: string;
  shortName: string;
  score: number;
  weight: number;
}

export interface Signal {
  id: string;
  pair: Pair;
  direction: Direction;
  confluenceScore: number;
  strength: SignalStrength;
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  tp3: number;
  rr: number;
  timeframe: string;
  style: TradingStyle;
  modules: ModuleScore[];
  createdAt: string;
  expiresAt: string;
  regime: 'TRENDING' | 'RANGING' | 'TRANSITIONAL';
  killZoneActive: boolean;
  killZoneName?: string;
  newsRisk: boolean;
  htfConflict: boolean;
}

export interface JournalEntry {
  id: string;
  signalId: string;
  pair: Pair;
  direction: Direction;
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  tp3: number;
  exitPrice?: number;
  pnlUsd?: number;
  pnlPips?: number;
  rrAchieved?: number;
  outcome?: 'tp1' | 'tp2' | 'tp3' | 'sl' | 'manual';
  confluenceScore: number;
  openedAt: string;
  closedAt?: string;
  holdDuration?: number;
  isPaper: boolean;
  notes?: string;
  postMortem?: string;
}

export interface CalendarEvent {
  id: string;
  title: string;
  time: string;
  impact: 'high' | 'medium' | 'low';
  currency: string;
  forecast?: string;
  previous?: string;
  actual?: string;
  pairs: Pair[];
}

export interface UserProfile {
  id: string;
  email: string;
  subscriptionTier: 'free' | 'premium' | 'pro';
  uiMode: UIMode;
  tradingStyle: TradingStyle;
  activePairs: Pair[];
  timezone: string;
  paperBalance: number;
  liveBalance?: number;
}
