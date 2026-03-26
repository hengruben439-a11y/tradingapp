import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { colors } from '../theme';
import { GlassCard } from '../components/GlassCard';
import { ConfidenceRing } from '../components/ConfidenceRing';
import { LiveTicker } from '../components/LiveTicker';
import { MiniChart } from '../components/Chart';
import { generateSparkline } from '../services/mock';
import { useSignals } from '../services/signalEngine';
import type { Signal, Pair, TradingStyle } from '../types';

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

type PairFilter = 'ALL' | Pair;

const PAIR_FILTERS: { key: PairFilter; label: string }[] = [
  { key: 'ALL', label: 'All Pairs' },
  { key: 'XAUUSDB', label: '🥇 XAU/USD' },
  { key: 'GBPJPYB', label: '🇬🇧 GBP/JPY' },
];

const STYLE_FILTERS: { key: TradingStyle; label: string; short: string }[] = [
  { key: 'scalping', label: 'Scalping', short: 'Scalp' },
  { key: 'day_trading', label: 'Day Trading', short: 'Day' },
  { key: 'swing_trading', label: 'Swing', short: 'Swing' },
  { key: 'position_trading', label: 'Position', short: 'Pos' },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function decayedScore(sig: Signal): number {
  const total = new Date(sig.expiresAt).getTime() - new Date(sig.createdAt).getTime();
  const elapsed = Date.now() - new Date(sig.createdAt).getTime();
  const frac = Math.min(1, Math.max(0, elapsed / total));
  return sig.confluenceScore * (1 - 0.25 * frac);
}

function elapsed(createdAt: string): string {
  const ms = Date.now() - new Date(createdAt).getTime();
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ${m % 60}m ago`;
}

function timeLeft(expiresAt: string): string {
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return 'Expired';
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m}m left`;
  return `${Math.floor(m / 60)}h ${m % 60}m left`;
}

function strengthLabel(score: number): string {
  if (score >= 0.80) return 'Very Strong';
  if (score >= 0.65) return 'Strong';
  if (score >= 0.50) return 'Moderate';
  return 'Watch';
}

function styleLabel(style: TradingStyle): string {
  switch (style) {
    case 'scalping': return 'Scalp';
    case 'day_trading': return 'Day';
    case 'swing_trading': return 'Swing';
    case 'position_trading': return 'Pos';
  }
}

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 600,
      padding: '2px 7px', borderRadius: 4,
      background: `${color}18`,
      color,
      border: `1px solid ${color}30`,
      whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// PriceBox
// ---------------------------------------------------------------------------

function PriceBox({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div style={{
      background: `${accent}0D`,
      border: `1px solid ${accent}20`,
      borderRadius: 8,
      padding: '7px 10px',
    }}>
      <div style={{ fontSize: 9, color: colors.textMuted, marginBottom: 2, textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {label}
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, color: accent, fontFamily: "'SF Mono', 'Fira Code', monospace" }}>
        {value}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Signal Card
// ---------------------------------------------------------------------------

const sparklineCache = new Map<string, number[]>();

function getSparkline(sig: Signal): number[] {
  if (!sparklineCache.has(sig.id)) {
    const base = sig.entry;
    const volatile = sig.pair === 'XAUUSDB' ? 4.5 : 0.45;
    sparklineCache.set(sig.id, generateSparkline(base, 28, volatile));
  }
  return sparklineCache.get(sig.id)!;
}

function SignalCard({ signal }: { signal: Signal }) {
  const navigate = useNavigate();
  const [hovered, setHovered] = useState(false);
  const score = decayedScore(signal);
  const isBuy = signal.direction === 'BUY';
  const dirColor = isBuy ? colors.buyGreen : colors.sellRed;
  const dirAlpha = isBuy ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)';
  const fmt = (n: number) => signal.pair === 'XAUUSDB' ? n.toFixed(2) : n.toFixed(3);
  const sparkline = getSparkline(signal);

  return (
    <div
      onClick={() => navigate(`/signal/${signal.id}`)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: 'rgba(26,26,46,0.6)',
        backdropFilter: 'blur(20px) saturate(150%)',
        WebkitBackdropFilter: 'blur(20px) saturate(150%)',
        border: `1px solid ${hovered ? 'rgba(212,168,67,0.28)' : score >= 0.80 ? colors.goldPrimary : 'rgba(212,168,67,0.12)'}`,
        borderRadius: 16,
        boxShadow: hovered
          ? '0 12px 40px rgba(0,0,0,0.5), 0 0 24px rgba(212,168,67,0.10)'
          : score >= 0.80
          ? '0 8px 32px rgba(0,0,0,0.4), 0 0 20px rgba(212,168,67,0.12)'
          : '0 8px 32px rgba(0,0,0,0.3)',
        cursor: 'pointer',
        transition: 'all 0.18s ease',
        transform: hovered ? 'translateY(-1px)' : 'none',
        marginBottom: 12,
        overflow: 'hidden',
      }}
    >
      {/* Top accent line for very-strong signals */}
      {score >= 0.80 && (
        <div style={{
          height: 2,
          background: `linear-gradient(90deg, ${colors.goldPrimary}00, ${colors.goldPrimary}, ${colors.goldPrimary}00)`,
        }} />
      )}

      <div style={{ padding: '14px 16px' }}>
        {/* Row 1: pair + timeframe / confidence ring */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 20 }}>{signal.pair === 'XAUUSDB' ? '🥇' : '🇬🇧'}</span>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 15, fontWeight: 800, color: colors.textPrimary, letterSpacing: 0.3 }}>
                  {signal.pair}
                </span>
                <span style={{
                  fontSize: 10, fontWeight: 600,
                  padding: '1px 6px', borderRadius: 4,
                  background: 'rgba(255,255,255,0.08)',
                  color: colors.textMuted,
                }}>
                  {signal.timeframe}
                </span>
                <span style={{
                  fontSize: 10, fontWeight: 600,
                  padding: '1px 6px', borderRadius: 4,
                  background: 'rgba(212,168,67,0.10)',
                  color: colors.goldPrimary,
                }}>
                  {styleLabel(signal.style)}
                </span>
              </div>
              <div style={{ fontSize: 10, color: colors.textMuted, marginTop: 1 }}>
                {elapsed(signal.createdAt)}
              </div>
            </div>
          </div>
          <ConfidenceRing score={score} size={60} />
        </div>

        {/* Row 2: Direction + sparkline */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 16px',
              borderRadius: 10,
              background: dirAlpha,
              border: `1px solid ${dirColor}35`,
            }}>
              <span style={{ fontSize: 22, fontWeight: 900, color: dirColor, letterSpacing: 2 }}>
                {signal.direction}
              </span>
              <span style={{ fontSize: 10, fontWeight: 700, color: dirColor, opacity: 0.85 }}>
                {strengthLabel(score)}
              </span>
            </div>
          </div>
          <MiniChart prices={sparkline} direction={signal.direction} width={110} height={38} />
        </div>

        {/* Row 3: Price grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 6, marginBottom: 12 }}>
          <PriceBox label="Entry" value={fmt(signal.entry)} accent={colors.textPrimary} />
          <PriceBox label="SL" value={fmt(signal.sl)} accent={colors.sellRed} />
          <PriceBox label="TP1" value={fmt(signal.tp1)} accent={colors.buyGreen} />
          <PriceBox label="TP2" value={fmt(signal.tp2)} accent='#4ADE80' />
        </div>

        {/* Row 4: Footer badges */}
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', alignItems: 'center' }}>
          <Badge
            label={signal.regime}
            color={signal.regime === 'TRENDING' ? colors.buyGreen : signal.regime === 'RANGING' ? colors.warning : colors.info}
          />
          {signal.killZoneActive && signal.killZoneName && (
            <Badge label={`⚡ ${signal.killZoneName}`} color={colors.goldPrimary} />
          )}
          {signal.newsRisk && <Badge label="⚠ News" color={colors.sellRed} />}
          {signal.htfConflict && <Badge label="⚔ HTF" color={colors.warning} />}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: colors.goldPrimary }}>
              R:R {signal.rr.toFixed(1)}
            </span>
            <span style={{ fontSize: 10, color: colors.textMuted }}>
              {timeLeft(signal.expiresAt)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat Card
// ---------------------------------------------------------------------------

function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <GlassCard style={{ padding: '12px 14px' }}>
      <div style={{ fontSize: 10, color: colors.textMuted, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {label}
      </div>
      <div style={{ fontSize: 20, fontWeight: 800, color: color ?? colors.textPrimary, lineHeight: 1 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 10, color: colors.textMuted, marginTop: 3 }}>{sub}</div>
      )}
    </GlassCard>
  );
}

// ---------------------------------------------------------------------------
// Pill button
// ---------------------------------------------------------------------------

function Pill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '6px 14px',
        borderRadius: 20,
        border: active ? `1px solid ${colors.goldPrimary}` : '1px solid rgba(255,255,255,0.10)',
        background: active ? `rgba(212,168,67,0.15)` : 'rgba(255,255,255,0.05)',
        color: active ? colors.goldPrimary : colors.textSecondary,
        fontSize: 12,
        fontWeight: active ? 700 : 500,
        cursor: 'pointer',
        whiteSpace: 'nowrap',
        flexShrink: 0,
        transition: 'all 0.15s ease',
        letterSpacing: 0.2,
      }}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export function Dashboard() {
  const [pairFilter, setPairFilter] = useState<PairFilter>('ALL');
  const [styleFilter, setStyleFilter] = useState<TradingStyle | 'all'>('all');

  const signals = useSignals();

  const filtered = signals.filter(s => {
    const pairMatch = pairFilter === 'ALL' || s.pair === pairFilter;
    const styleMatch = styleFilter === 'all' || s.style === styleFilter;
    return pairMatch && styleMatch;
  });

  const activeCount = signals.length;
  const scalping = signals.filter(s => s.style === 'scalping').length;

  return (
    <div>
      {/* Live Ticker */}
      <div style={{ margin: '0 -16px', marginTop: -8 }}>
        <LiveTicker />
      </div>

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginTop: 16, marginBottom: 16 }}>
        <StatCard label="Active" value={activeCount.toString()} sub="signals live" />
        <StatCard label="Today P&L" value="+$198" sub="paper mode" color={colors.buyGreen} />
        <StatCard label="Win Rate" value="68%" sub="TP1 · 7d" color={colors.goldPrimary} />
      </div>

      {/* Pair filter */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 10, overflowX: 'auto', paddingBottom: 2 }}>
        {PAIR_FILTERS.map(f => (
          <Pill key={f.key} label={f.label} active={pairFilter === f.key} onClick={() => setPairFilter(f.key)} />
        ))}
      </div>

      {/* Style filter */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 16, overflowX: 'auto', paddingBottom: 2 }}>
        <Pill label="All Styles" active={styleFilter === 'all'} onClick={() => setStyleFilter('all')} />
        {STYLE_FILTERS.map(f => (
          <Pill key={f.key} label={f.short} active={styleFilter === f.key} onClick={() => setStyleFilter(f.key)} />
        ))}
      </div>

      {/* Section header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: colors.textSecondary, letterSpacing: 0.3 }}>
          {styleFilter === 'all' ? 'All Signals' : STYLE_FILTERS.find(f => f.key === styleFilter)?.label ?? 'Signals'}
        </span>
        <span style={{ fontSize: 11, color: colors.textMuted }}>
          {filtered.length} of {activeCount} showing
          {scalping > 0 && styleFilter !== 'scalping' && (
            <span style={{ color: colors.goldPrimary }}> · {scalping} scalp{scalping > 1 ? 's' : ''} active</span>
          )}
        </span>
      </div>

      {/* Signal list */}
      {filtered.length === 0 ? (
        <GlassCard style={{ padding: 40, textAlign: 'center' }}>
          <div style={{ marginBottom: 12 }}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" style={{ margin: '0 auto' }}>
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="rgba(212,168,67,0.4)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div style={{ fontSize: 15, fontWeight: 700, color: colors.textSecondary, marginBottom: 6 }}>
            No {styleFilter !== 'all' ? (STYLE_FILTERS.find(f => f.key === styleFilter)?.label ?? styleFilter) : ''} signals right now
          </div>
          <div style={{ fontSize: 12, color: colors.textMuted, lineHeight: 1.6 }}>
            The engine is scanning for high-confluence setups.
            {styleFilter !== 'all' && (
              <><br /><span
                style={{ color: colors.goldPrimary, cursor: 'pointer' }}
                onClick={() => setStyleFilter('all')}
              >View all styles →</span></>
            )}
          </div>
        </GlassCard>
      ) : (
        filtered.map(sig => <SignalCard key={sig.id} signal={sig} />)
      )}
    </div>
  );
}
