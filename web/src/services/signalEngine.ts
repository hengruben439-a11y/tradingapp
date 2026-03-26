/**
 * Client-side signal simulation engine.
 *
 * Generates new signals on a rolling basis using the same confluence logic
 * structure as the real engine. In production this will be replaced by
 * WebSocket push from the FastAPI backend. Until then, this provides a
 * realistic dynamic signal feed in the UI.
 */

import type { Signal, Pair, TradingStyle } from '../types';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

// How often to attempt generating a new signal (ms). Not every attempt produces one.
const SIGNAL_GEN_INTERVAL_MS = 25_000; // every 25s

// Max simultaneous live signals
const MAX_SIGNALS = 6;

// Base price reference (will be updated by live ticker)
let _xauPrice = 4434.00;
let _gjPrice = 213.00;

export function updateBasePrices(xau: number, gj: number) {
  _xauPrice = xau;
  _gjPrice = gj;
}

// ---------------------------------------------------------------------------
// Module score generator — mirrors the real engine's output range
// ---------------------------------------------------------------------------

type ModuleConfig = { name: string; shortName: string; weight: number };

const XAU_MODULES: ModuleConfig[] = [
  { name: 'Market Structure', shortName: 'MS', weight: 25 },
  { name: 'Order Blocks + FVG', shortName: 'OB/FVG', weight: 20 },
  { name: 'OTE Fibonacci', shortName: 'OTE', weight: 15 },
  { name: 'EMA Alignment', shortName: 'EMA', weight: 10 },
  { name: 'RSI (14)', shortName: 'RSI', weight: 8 },
  { name: 'MACD', shortName: 'MACD', weight: 7 },
  { name: 'Bollinger Bands', shortName: 'BB', weight: 5 },
  { name: 'Kill Zone', shortName: 'KZ', weight: 5 },
  { name: 'S&R Levels', shortName: 'S&R', weight: 5 },
];

const GJ_MODULES: ModuleConfig[] = [
  { name: 'Market Structure', shortName: 'MS', weight: 25 },
  { name: 'Order Blocks + FVG', shortName: 'OB/FVG', weight: 18 },
  { name: 'OTE Fibonacci', shortName: 'OTE', weight: 15 },
  { name: 'EMA Alignment', shortName: 'EMA', weight: 12 },
  { name: 'RSI (14)', shortName: 'RSI', weight: 8 },
  { name: 'MACD', shortName: 'MACD', weight: 7 },
  { name: 'Bollinger Bands', shortName: 'BB', weight: 5 },
  { name: 'Kill Zone', shortName: 'KZ', weight: 5 },
  { name: 'S&R Levels', shortName: 'S&R', weight: 5 },
];

function rand(min: number, max: number) {
  return min + Math.random() * (max - min);
}

function generateModuleScores(modules: ModuleConfig[], direction: 'BUY' | 'SELL') {
  const dirSign = direction === 'BUY' ? 1 : -1;

  return modules.map(m => {
    // Most modules agree with the direction; ~1-2 dissent (realistic)
    const agrees = Math.random() > 0.22;
    const magnitude = rand(0.45, 0.92);
    const score = agrees ? dirSign * magnitude : -dirSign * rand(0.20, 0.55);
    return { ...m, score: parseFloat(score.toFixed(2)) };
  });
}

function computeConfluence(modules: ReturnType<typeof generateModuleScores>): number {
  const totalWeight = modules.reduce((s, m) => s + m.weight, 0);
  const weighted = modules.reduce((s, m) => s + m.score * m.weight, 0);
  const raw = weighted / totalWeight;
  return Math.min(0.97, Math.max(-0.97, raw));
}

// ---------------------------------------------------------------------------
// TP/SL calculation — mirrors engine/tp_sl.py logic
// ---------------------------------------------------------------------------

function calcLevels(
  basePrice: number,
  direction: 'BUY' | 'SELL',
  atrMultiple: number,
  pair: Pair,
): { entry: number; sl: number; tp1: number; tp2: number; tp3: number; rr: number } {
  const isXau = pair.startsWith('XAU');
  // ATR as % of price: XAU ~0.3%, GJ ~0.25%
  const atr = isXau ? basePrice * 0.003 : basePrice * 0.0025;

  const entry = basePrice + (direction === 'BUY' ? -atr * 0.1 : atr * 0.1);
  const slDist = atr * atrMultiple;
  const sl = direction === 'BUY' ? entry - slDist : entry + slDist;
  const tp1 = direction === 'BUY' ? entry + slDist * 1.2 : entry - slDist * 1.2;
  const tp2 = direction === 'BUY' ? entry + slDist * 2.0 : entry - slDist * 2.0;
  const tp3 = direction === 'BUY' ? entry + slDist * 3.0 : entry - slDist * 3.0;
  const rr = parseFloat((Math.abs(tp2 - entry) / slDist).toFixed(1));

  const dp = isXau ? 2 : 3;
  const fix = (n: number) => parseFloat(n.toFixed(dp));
  return { entry: fix(entry), sl: fix(sl), tp1: fix(tp1), tp2: fix(tp2), tp3: fix(tp3), rr };
}

// ---------------------------------------------------------------------------
// Signal builder
// ---------------------------------------------------------------------------

const STYLES: TradingStyle[] = ['scalping', 'day_trading', 'swing_trading'];
const TFS: Record<TradingStyle, string[]> = {
  scalping: ['1m', '5m'],
  day_trading: ['15m', '30m'],
  swing_trading: ['1H', '4H'],
  position_trading: ['1D'],
};
const EXPIRY_BARS: Record<string, number> = {
  '1m': 5, '5m': 8, '15m': 12, '30m': 16, '1H': 20, '4H': 48,
};
const KILL_ZONES = ['New York', 'London', 'Asian', 'Shanghai Open'];
const REGIMES = ['TRENDING', 'RANGING', 'TRANSITIONAL'] as const;

let _idCounter = 100;

export function generateSignal(): Signal | null {
  // ~50% chance of actually producing a signal this tick
  if (Math.random() > 0.5) return null;

  const pair: Pair = Math.random() > 0.5 ? 'XAUUSDB' : 'GBPJPYB';
  const direction: 'BUY' | 'SELL' = Math.random() > 0.5 ? 'BUY' : 'SELL';
  const style: TradingStyle = STYLES[Math.floor(Math.random() * STYLES.length)];
  const timeframe = TFS[style][Math.floor(Math.random() * TFS[style].length)];

  const basePrice = pair.startsWith('XAU') ? _xauPrice : _gjPrice;
  const modules = pair.startsWith('XAU')
    ? generateModuleScores(XAU_MODULES, direction)
    : generateModuleScores(GJ_MODULES, direction);

  const rawScore = computeConfluence(modules);
  const absScore = Math.abs(rawScore);

  // Only emit signals that pass the 0.50 threshold
  if (absScore < 0.50) return null;

  const strength = absScore >= 0.80 ? 'very_strong'
    : absScore >= 0.65 ? 'strong'
    : 'moderate';

  const atrMultiple = style === 'scalping' ? rand(1.0, 1.5)
    : style === 'day_trading' ? rand(1.3, 2.0)
    : rand(1.8, 2.8);

  const levels = calcLevels(basePrice, direction, atrMultiple, pair);

  const now = new Date();
  const expiryBars = EXPIRY_BARS[timeframe] ?? 12;
  const barMs = timeframe === '1m' ? 60_000 : timeframe === '5m' ? 300_000
    : timeframe === '15m' ? 900_000 : timeframe === '30m' ? 1_800_000
    : timeframe === '1H' ? 3_600_000 : 14_400_000;

  const killZoneActive = Math.random() > 0.4;
  const regime = REGIMES[Math.floor(Math.random() * REGIMES.length)];

  return {
    id: `sig_gen_${++_idCounter}`,
    pair,
    direction,
    confluenceScore: parseFloat(absScore.toFixed(2)),
    strength,
    ...levels,
    timeframe,
    style,
    modules,
    createdAt: now.toISOString(),
    expiresAt: new Date(now.getTime() + expiryBars * barMs).toISOString(),
    regime,
    killZoneActive,
    killZoneName: killZoneActive ? KILL_ZONES[Math.floor(Math.random() * KILL_ZONES.length)] : undefined,
    newsRisk: Math.random() > 0.85,
    htfConflict: Math.random() > 0.80,
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

import { useState, useEffect } from 'react';
import { mockSignals } from './mock';

export function useSignals() {
  const [signals, setSignals] = useState<Signal[]>(mockSignals);

  useEffect(() => {
    const interval = setInterval(() => {
      setSignals(prev => {
        // Remove expired signals
        const now = Date.now();
        const live = prev.filter(s => new Date(s.expiresAt).getTime() > now);

        if (live.length >= MAX_SIGNALS) return live;

        const newSig = generateSignal();
        if (!newSig) return live;

        // De-duplicate: skip if same pair + direction + style already active
        const duplicate = live.some(s =>
          s.pair === newSig.pair &&
          s.direction === newSig.direction &&
          s.style === newSig.style
        );
        if (duplicate) return live;

        // Newest first
        return [newSig, ...live];
      });
    }, SIGNAL_GEN_INTERVAL_MS);

    return () => clearInterval(interval);
  }, []);

  return signals;
}
