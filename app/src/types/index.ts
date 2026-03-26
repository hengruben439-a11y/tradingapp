export type TradingStyle = 'scalping' | 'day_trading' | 'swing_trading' | 'position_trading';
export type SignalDirection = 'BUY' | 'SELL';
export type SignalStrength = 'very_strong' | 'strong' | 'moderate' | 'weak';
export type UIMode = 'simple' | 'pro' | 'max';
export type MarketRegime = 'trending' | 'ranging' | 'transitional' | 'unknown';

export interface Signal {
  id: string;
  pair: 'XAUUSD' | 'GBPJPY';
  direction: SignalDirection;
  strength: SignalStrength;
  confluenceScore: number;   // 0-1 base score
  decayedScore: number;      // real-time decayed score
  entryPrice: number;
  stopLoss: number;
  tp1: number;
  tp2: number;
  tp3: number;
  riskPips: number;
  lotSize: number;
  dollarRisk: number;
  generatedAt: string;       // ISO
  expiresAt: string;         // ISO
  tradingStyle: TradingStyle;
  killZone?: string;
  regime: MarketRegime;
  hasNewsRisk: boolean;
  hasHTFConflict: boolean;
  timeframe: string;
  // Pro/Max mode fields
  moduleScores?: Record<string, number>;
  dissent?: Array<{ module: string; score: number; weight: number }>;
  rationale?: string;
  htfConflictDescription?: string;
}

export interface JournalEntry {
  id: string;
  signalId?: string;
  pair: string;
  direction: SignalDirection;
  entryPrice: number;
  exitPrice?: number;
  stopLoss: number;
  tp1: number;
  tp2: number;
  tp3: number;
  lotSize: number;
  pnlPips?: number;
  pnlUsd?: number;
  rrAchieved?: number;
  status: 'open' | 'tp1_hit' | 'tp2_hit' | 'tp3_hit' | 'sl_hit' | 'expired' | 'manual_close';
  entryTime: string;
  exitTime?: string;
  notes?: string;
  postMortem?: {
    failedModule: string;
    whatHappened: string;
    lesson: string;
  };
  newsFlag: boolean;
  isLive: boolean; // false = paper trade
  tradingStyle?: TradingStyle;
  timeframe?: string;
  confluenceScore?: number;
}

export interface CalendarEvent {
  id: string;
  title: string;
  datetime: string;    // ISO UTC
  impact: 'high' | 'medium' | 'low';
  pairsAffected: string[];
  actual?: string;
  forecast?: string;
  previous?: string;
  currency: string;
  country?: string;
}

export interface UserProfile {
  id: string;
  email: string;
  tradingStyle: TradingStyle;
  uiMode: UIMode;
  pairs: string[];
  timezone: string;
  riskPct: number;
  accountBalance: number;
  subscriptionTier: 'free' | 'premium' | 'pro';
  avatarUrl?: string;
  displayName?: string;
}

export interface AnalyticsSummary {
  totalTrades: number;
  winRate: number;
  profitFactor: number;
  avgRR: number;
  totalPnlUsd: number;
  maxDrawdownPct: number;
  sharpeRatio: number;
  currentStreak: number;
  bestTrade: number;
  worstTrade: number;
}

export interface EquityCurvePoint {
  date: string;
  equity: number;
  drawdown: number;
}

export interface MonthlyPnl {
  year: number;
  month: number;
  pnl: number;
  trades: number;
  winRate: number;
}

export interface WebSocketEvent {
  type: 'signal' | 'tp_hit' | 'sl_hit' | 'news_alert' | 'pong';
  payload: unknown;
  timestamp: string;
}

export interface NewsAlert {
  eventId: string;
  title: string;
  impact: 'high' | 'medium' | 'low';
  minutesUntil: number;
  pairsAffected: string[];
}

export interface RiskCalculation {
  lotSize: number;
  dollarRisk: number;
  marginRequired: number;
  pipValue: number;
  riskPips: number;
}
