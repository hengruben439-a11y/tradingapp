import type { Signal, JournalEntry, CalendarEvent, UserProfile } from '../types';

export const mockUser: UserProfile = {
  id: 'usr_001',
  email: 'trader@made.app',
  subscriptionTier: 'pro',
  uiMode: 'pro',
  tradingStyle: 'day_trading',
  activePairs: ['XAUUSDB', 'GBPJPYB'],
  timezone: 'SGT',
  paperBalance: 12_340.50,
  liveBalance: 8_500.00,
};

const now = new Date();
const mins = (n: number) => new Date(now.getTime() + n * 60_000).toISOString();

export const mockSignals: Signal[] = [
  // --- SCALPING: XAU BUY (1m, very strong) — current ~4434 ---
  {
    id: 'sig_001',
    pair: 'XAUUSDB',
    direction: 'BUY',
    confluenceScore: 0.83,
    strength: 'very_strong',
    entry: 4433.50,
    sl: 4428.20,
    tp1: 4439.00,
    tp2: 4446.50,
    tp3: 4455.00,
    rr: 2.2,
    timeframe: '1m',
    style: 'scalping',
    modules: [
      { name: 'Market Structure', shortName: 'MS', score: 0.85, weight: 25 },
      { name: 'Order Blocks + FVG', shortName: 'OB/FVG', score: 0.90, weight: 20 },
      { name: 'OTE Fibonacci', shortName: 'OTE', score: 0.78, weight: 15 },
      { name: 'EMA Alignment', shortName: 'EMA', score: 0.70, weight: 10 },
      { name: 'RSI (14)', shortName: 'RSI', score: 0.65, weight: 8 },
      { name: 'MACD', shortName: 'MACD', score: 0.72, weight: 7 },
      { name: 'Bollinger Bands', shortName: 'BB', score: -0.25, weight: 5 },
      { name: 'Kill Zone', shortName: 'KZ', score: 0.80, weight: 5 },
      { name: 'S&R Levels', shortName: 'S&R', score: 0.75, weight: 5 },
    ],
    createdAt: mins(-4),
    expiresAt: mins(21),
    regime: 'TRENDING',
    killZoneActive: true,
    killZoneName: 'New York',
    newsRisk: false,
    htfConflict: false,
  },

  // --- SCALPING: GJ SELL (5m, strong) — current ~213 ---
  {
    id: 'sig_002',
    pair: 'GBPJPYB',
    direction: 'SELL',
    confluenceScore: 0.71,
    strength: 'strong',
    entry: 213.480,
    sl: 213.820,
    tp1: 212.960,
    tp2: 212.340,
    tp3: 211.500,
    rr: 1.9,
    timeframe: '5m',
    style: 'scalping',
    modules: [
      { name: 'Market Structure', shortName: 'MS', score: -0.80, weight: 25 },
      { name: 'Order Blocks + FVG', shortName: 'OB/FVG', score: -0.75, weight: 18 },
      { name: 'OTE Fibonacci', shortName: 'OTE', score: -0.60, weight: 15 },
      { name: 'EMA Alignment', shortName: 'EMA', score: -0.70, weight: 12 },
      { name: 'RSI (14)', shortName: 'RSI', score: -0.55, weight: 8 },
      { name: 'MACD', shortName: 'MACD', score: 0.25, weight: 7 },
      { name: 'Bollinger Bands', shortName: 'BB', score: -0.50, weight: 5 },
      { name: 'Kill Zone', shortName: 'KZ', score: -0.80, weight: 5 },
      { name: 'S&R Levels', shortName: 'S&R', score: -0.60, weight: 5 },
    ],
    createdAt: mins(-7),
    expiresAt: mins(33),
    regime: 'TRENDING',
    killZoneActive: true,
    killZoneName: 'New York',
    newsRisk: false,
    htfConflict: false,
  },

  // --- DAY TRADING: XAU SELL (15m, strong) ---
  {
    id: 'sig_003',
    pair: 'XAUUSDB',
    direction: 'SELL',
    confluenceScore: 0.68,
    strength: 'strong',
    entry: 4442.00,
    sl: 4449.50,
    tp1: 4434.00,
    tp2: 4424.00,
    tp3: 4410.00,
    rr: 2.1,
    timeframe: '15m',
    style: 'day_trading',
    modules: [
      { name: 'Market Structure', shortName: 'MS', score: -0.75, weight: 25 },
      { name: 'Order Blocks + FVG', shortName: 'OB/FVG', score: -0.65, weight: 20 },
      { name: 'OTE Fibonacci', shortName: 'OTE', score: -0.55, weight: 15 },
      { name: 'EMA Alignment', shortName: 'EMA', score: -0.60, weight: 10 },
      { name: 'RSI (14)', shortName: 'RSI', score: -0.70, weight: 8 },
      { name: 'MACD', shortName: 'MACD', score: -0.45, weight: 7 },
      { name: 'Bollinger Bands', shortName: 'BB', score: -0.50, weight: 5 },
      { name: 'Kill Zone', shortName: 'KZ', score: 0.30, weight: 5 },
      { name: 'S&R Levels', shortName: 'S&R', score: -0.55, weight: 5 },
    ],
    createdAt: mins(-28),
    expiresAt: mins(68),
    regime: 'TRANSITIONAL',
    killZoneActive: false,
    newsRisk: true,
    htfConflict: true,
  },

  // --- DAY TRADING: GJ BUY (30m, moderate) ---
  {
    id: 'sig_004',
    pair: 'GBPJPYB',
    direction: 'BUY',
    confluenceScore: 0.61,
    strength: 'moderate',
    entry: 212.640,
    sl: 212.180,
    tp1: 213.280,
    tp2: 213.920,
    tp3: 214.800,
    rr: 1.8,
    timeframe: '30m',
    style: 'day_trading',
    modules: [
      { name: 'Market Structure', shortName: 'MS', score: 0.65, weight: 25 },
      { name: 'Order Blocks + FVG', shortName: 'OB/FVG', score: 0.60, weight: 18 },
      { name: 'OTE Fibonacci', shortName: 'OTE', score: 0.70, weight: 15 },
      { name: 'EMA Alignment', shortName: 'EMA', score: 0.50, weight: 12 },
      { name: 'RSI (14)', shortName: 'RSI', score: 0.55, weight: 8 },
      { name: 'MACD', shortName: 'MACD', score: 0.40, weight: 7 },
      { name: 'Bollinger Bands', shortName: 'BB', score: 0.30, weight: 5 },
      { name: 'Kill Zone', shortName: 'KZ', score: -0.30, weight: 5 },
      { name: 'S&R Levels', shortName: 'S&R', score: 0.65, weight: 5 },
    ],
    createdAt: mins(-55),
    expiresAt: mins(121),
    regime: 'RANGING',
    killZoneActive: false,
    newsRisk: false,
    htfConflict: false,
  },

  // --- SWING TRADING: XAU BUY (4H, very strong) ---
  {
    id: 'sig_005',
    pair: 'XAUUSDB',
    direction: 'BUY',
    confluenceScore: 0.86,
    strength: 'very_strong',
    entry: 4428.00,
    sl: 4400.00,
    tp1: 4456.00,
    tp2: 4490.00,
    tp3: 4535.00,
    rr: 3.1,
    timeframe: '4H',
    style: 'swing_trading',
    modules: [
      { name: 'Market Structure', shortName: 'MS', score: 0.85, weight: 25 },
      { name: 'Order Blocks + FVG', shortName: 'OB/FVG', score: 0.85, weight: 20 },
      { name: 'OTE Fibonacci', shortName: 'OTE', score: 0.80, weight: 15 },
      { name: 'EMA Alignment', shortName: 'EMA', score: 0.75, weight: 10 },
      { name: 'RSI (14)', shortName: 'RSI', score: 0.60, weight: 8 },
      { name: 'MACD', shortName: 'MACD', score: 0.70, weight: 7 },
      { name: 'Bollinger Bands', shortName: 'BB', score: 0.45, weight: 5 },
      { name: 'Kill Zone', shortName: 'KZ', score: 0.80, weight: 5 },
      { name: 'S&R Levels', shortName: 'S&R', score: 0.80, weight: 5 },
    ],
    createdAt: mins(-210),
    expiresAt: mins(870),
    regime: 'TRENDING',
    killZoneActive: true,
    killZoneName: 'London',
    newsRisk: false,
    htfConflict: false,
  },
];

// ---------------------------------------------------------------------------
// Sparkline generator
// ---------------------------------------------------------------------------

export function generateSparkline(basePrice: number, bars: number, volatile: number): number[] {
  const prices: number[] = [];
  let current = basePrice;
  for (let i = 0; i < bars; i++) {
    const change = (Math.random() - 0.5) * 2 * volatile;
    current = current + change;
    prices.push(current);
  }
  return prices;
}

// ---------------------------------------------------------------------------
// Live price fallback (used until real fetch resolves)
// ---------------------------------------------------------------------------

export const LIVE_PRICES = {
  XAUUSDB: { bid: 4433.80, ask: 4434.20, change: +18.50, changePct: +0.42 },
  GBPJPYB: { bid: 212.945, ask: 212.965, change: -0.54, changePct: -0.25 },
};

// ---------------------------------------------------------------------------
// Mock journal
// ---------------------------------------------------------------------------

export const mockJournal: JournalEntry[] = [
  {
    id: 'je_001',
    signalId: 'sig_h001',
    pair: 'XAUUSDB',
    direction: 'BUY',
    entry: 4398.50,
    sl: 4384.00,
    tp1: 4412.00,
    tp2: 4428.00,
    tp3: 4446.00,
    exitPrice: 4428.00,
    pnlUsd: 198.00,
    pnlPips: 29.5,
    rrAchieved: 2.03,
    outcome: 'tp2',
    confluenceScore: 0.79,
    openedAt: new Date(now.getTime() - 2 * 86400_000).toISOString(),
    closedAt: new Date(now.getTime() - 2 * 86400_000 + 5 * 3600_000).toISOString(),
    holdDuration: 5 * 60,
    isPaper: false,
  },
  {
    id: 'je_002',
    signalId: 'sig_h002',
    pair: 'GBPJPYB',
    direction: 'BUY',
    entry: 212.420,
    sl: 211.880,
    tp1: 213.160,
    tp2: 213.980,
    tp3: 215.200,
    exitPrice: 211.880,
    pnlUsd: -95.00,
    pnlPips: -54,
    rrAchieved: -1.0,
    outcome: 'sl',
    confluenceScore: 0.67,
    openedAt: new Date(now.getTime() - 3 * 86400_000).toISOString(),
    closedAt: new Date(now.getTime() - 3 * 86400_000 + 2 * 3600_000).toISOString(),
    holdDuration: 120,
    isPaper: false,
    postMortem: 'Order Block was mitigated — price swept through the zone due to a BOJ rate decision. The OB was invalidated by a bearish CHoCH on the 4H timeframe 30 minutes after entry. HTF structure shifted bearish against the trade.',
  },
  {
    id: 'je_003',
    signalId: 'sig_h003',
    pair: 'XAUUSDB',
    direction: 'BUY',
    entry: 4412.00,
    sl: 4398.50,
    tp1: 4425.00,
    tp2: 4440.00,
    tp3: 4458.00,
    exitPrice: 4458.00,
    pnlUsd: 330.00,
    pnlPips: 44,
    rrAchieved: 3.26,
    outcome: 'tp3',
    confluenceScore: 0.87,
    openedAt: new Date(now.getTime() - 5 * 86400_000).toISOString(),
    closedAt: new Date(now.getTime() - 5 * 86400_000 + 8 * 3600_000).toISOString(),
    holdDuration: 480,
    isPaper: false,
  },
  {
    id: 'je_004',
    signalId: 'sig_h004',
    pair: 'GBPJPYB',
    direction: 'SELL',
    entry: 214.650,
    sl: 215.230,
    tp1: 213.870,
    tp2: 213.150,
    tp3: 212.100,
    exitPrice: 213.870,
    pnlUsd: 110.00,
    pnlPips: 78,
    rrAchieved: 1.34,
    outcome: 'tp1',
    confluenceScore: 0.72,
    openedAt: new Date(now.getTime() - 7 * 86400_000).toISOString(),
    closedAt: new Date(now.getTime() - 7 * 86400_000 + 3 * 3600_000).toISOString(),
    holdDuration: 180,
    isPaper: false,
  },
];

// ---------------------------------------------------------------------------
// Mock calendar
// ---------------------------------------------------------------------------

export const mockCalendar: CalendarEvent[] = [
  {
    id: 'ev_001',
    title: 'US CPI (MoM)',
    time: new Date(now.getTime() + 45 * 60_000).toISOString(),
    impact: 'high',
    currency: 'USD',
    forecast: '0.3%',
    previous: '0.2%',
    pairs: ['XAUUSDB', 'GBPJPYB'],
  },
  {
    id: 'ev_002',
    title: 'FOMC Minutes',
    time: new Date(now.getTime() + 3 * 3600_000).toISOString(),
    impact: 'high',
    currency: 'USD',
    forecast: undefined,
    previous: undefined,
    pairs: ['XAUUSDB', 'GBPJPYB'],
  },
  {
    id: 'ev_003',
    title: 'UK GDP (QoQ)',
    time: new Date(now.getTime() + 6 * 3600_000).toISOString(),
    impact: 'high',
    currency: 'GBP',
    forecast: '0.4%',
    previous: '0.3%',
    pairs: ['GBPJPYB'],
  },
  {
    id: 'ev_004',
    title: 'BOJ Policy Rate',
    time: new Date(now.getTime() + 12 * 3600_000).toISOString(),
    impact: 'high',
    currency: 'JPY',
    forecast: '0.50%',
    previous: '0.50%',
    pairs: ['GBPJPYB'],
  },
  {
    id: 'ev_005',
    title: 'US Retail Sales',
    time: new Date(now.getTime() + 24 * 3600_000).toISOString(),
    impact: 'medium',
    currency: 'USD',
    forecast: '0.6%',
    previous: '0.4%',
    pairs: ['XAUUSDB', 'GBPJPYB'],
  },
  {
    id: 'ev_006',
    title: 'UK PMI Composite',
    time: new Date(now.getTime() + 28 * 3600_000).toISOString(),
    impact: 'medium',
    currency: 'GBP',
    forecast: '52.1',
    previous: '51.8',
    pairs: ['GBPJPYB'],
  },
];
