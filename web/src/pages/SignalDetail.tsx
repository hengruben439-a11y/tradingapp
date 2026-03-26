import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { colors } from '../theme';
import { GlassCard } from '../components/GlassCard';
import { ConfidenceRing } from '../components/ConfidenceRing';
import { SignalChart } from '../components/Chart';
import { mockSignals } from '../services/mock';
import type { ModuleScore, Signal } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function decayedScore(sig: Signal): number {
  const total = new Date(sig.expiresAt).getTime() - new Date(sig.createdAt).getTime();
  const elapsed = Date.now() - new Date(sig.createdAt).getTime();
  const frac = Math.min(1, Math.max(0, elapsed / total));
  return sig.confluenceScore * (1 - 0.25 * frac);
}

function elapsedFraction(sig: Signal): number {
  const total = new Date(sig.expiresAt).getTime() - new Date(sig.createdAt).getTime();
  const elapsed = Date.now() - new Date(sig.createdAt).getTime();
  return Math.min(1, Math.max(0, elapsed / total));
}

function timeLeft(expiresAt: string): string {
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return 'Expired';
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

function styleLabel(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 600,
      padding: '3px 8px', borderRadius: 4,
      background: `${color}18`,
      color,
      border: `1px solid ${color}30`,
    }}>
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Price Level Row (with left indicator bar)
// ---------------------------------------------------------------------------

function PriceLevel({
  label,
  value,
  accentColor,
  note,
  barWidth,
}: {
  label: string;
  value: string;
  accentColor: string;
  note?: string;
  barWidth?: number;
}) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '10px 0',
      borderBottom: '1px solid rgba(255,255,255,0.04)',
    }}>
      {/* Indicator bar */}
      <div style={{
        width: 3,
        height: note ? 38 : 28,
        borderRadius: 2,
        background: accentColor,
        flexShrink: 0,
        opacity: 0.9,
      }} />

      {/* Label + note */}
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 12, color: colors.textSecondary, fontWeight: 600 }}>{label}</div>
        {note && <div style={{ fontSize: 10, color: colors.textMuted, marginTop: 2 }}>{note}</div>}
      </div>

      {/* Optional mini bar */}
      {barWidth !== undefined && (
        <div style={{ width: 48, height: 3, background: 'rgba(255,255,255,0.06)', borderRadius: 2 }}>
          <div style={{
            height: '100%', borderRadius: 2,
            width: `${barWidth}%`,
            background: accentColor,
          }} />
        </div>
      )}

      {/* Value */}
      <span style={{
        fontSize: 16,
        fontWeight: 700,
        color: accentColor,
        fontFamily: "'SF Mono', 'Fira Code', monospace",
        minWidth: 80,
        textAlign: 'right',
      }}>
        {value}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Module Bar
// ---------------------------------------------------------------------------

function ModuleBar({ module, signalScore }: { module: ModuleScore; signalScore: number }) {
  const aligned = Math.sign(module.score) === Math.sign(signalScore) && Math.abs(module.score) > 0.1;
  const neutral = Math.abs(module.score) <= 0.1;
  const color = neutral ? colors.warning : aligned ? colors.buyGreen : colors.sellRed;
  const pct = Math.abs(module.score) * 100;
  const label = neutral ? 'Neutral' : aligned ? 'Aligned' : 'Opposing';

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 6, height: 6, borderRadius: '50%',
            background: color,
            boxShadow: `0 0 4px ${color}80`,
            flexShrink: 0,
          }} />
          <span style={{ fontSize: 12, color: colors.textPrimary, fontWeight: 600 }}>
            {module.name}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{
            fontSize: 9, fontWeight: 700,
            padding: '1px 5px', borderRadius: 3,
            background: `${color}15`,
            color,
          }}>
            {label}
          </span>
          <span style={{ fontSize: 10, color: colors.textMuted, minWidth: 28, textAlign: 'right' }}>
            {module.weight}%
          </span>
          <span style={{
            fontSize: 11, fontWeight: 700, color,
            fontFamily: "'SF Mono', 'Fira Code', monospace",
            minWidth: 40, textAlign: 'right',
          }}>
            {module.score >= 0 ? '+' : ''}{module.score.toFixed(2)}
          </span>
        </div>
      </div>
      <div style={{ height: 5, background: 'rgba(255,255,255,0.06)', borderRadius: 3 }}>
        <div style={{
          height: '100%', borderRadius: 3,
          width: `${pct}%`,
          background: `linear-gradient(90deg, ${color}90, ${color})`,
          boxShadow: `0 0 6px ${color}50`,
          transition: 'width 0.5s ease',
        }} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SignalDetail
// ---------------------------------------------------------------------------

export function SignalDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const signal = mockSignals.find(s => s.id === id);

  if (!signal) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <div style={{ color: colors.textSecondary, marginBottom: 16 }}>Signal not found</div>
        <button
          onClick={() => navigate('/')}
          style={{ color: colors.goldPrimary, background: 'none', border: 'none', cursor: 'pointer', fontSize: 14 }}
        >
          ← Back to Signals
        </button>
      </div>
    );
  }

  const score = decayedScore(signal);
  const frac = elapsedFraction(signal);
  const isBuy = signal.direction === 'BUY';
  const dirColor = isBuy ? colors.buyGreen : colors.sellRed;
  const fmt = (n: number) => signal.pair === 'XAUUSDB' ? n.toFixed(2) : n.toFixed(3);
  const opposing = signal.modules.filter(
    m => Math.sign(m.score) !== Math.sign(signal.confluenceScore) && Math.abs(m.score) > 0.15
  );

  // Decay bar color
  const decayPct = (score / signal.confluenceScore) * 100;
  const decayColor = decayPct > 75 ? colors.buyGreen : decayPct > 50 ? colors.goldPrimary : colors.warning;

  return (
    <div>
      {/* Back */}
      <button
        onClick={() => navigate('/')}
        style={{
          background: 'none', border: 'none',
          color: colors.goldPrimary,
          cursor: 'pointer',
          fontSize: 13, fontWeight: 600,
          marginBottom: 14,
          display: 'flex', alignItems: 'center', gap: 4,
          padding: 0,
        }}
      >
        ← Signals
      </button>

      {/* Header Card */}
      <GlassCard style={{ padding: 20, marginBottom: 10 }} highlighted={score >= 0.80}>
        {/* Pair + direction + ring */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 24 }}>{signal.pair === 'XAUUSDB' ? '🥇' : '🇬🇧'}</span>
              <span style={{ fontSize: 20, fontWeight: 800, color: colors.textPrimary, letterSpacing: 0.3 }}>
                {signal.pair}
              </span>
              <span style={{
                fontSize: 11, fontWeight: 600,
                padding: '2px 8px', borderRadius: 5,
                background: 'rgba(255,255,255,0.08)',
                color: colors.textMuted,
              }}>
                {signal.timeframe}
              </span>
            </div>
            <div style={{
              fontSize: 32, fontWeight: 900, color: dirColor,
              letterSpacing: 3, lineHeight: 1,
              textShadow: `0 0 20px ${dirColor}50`,
            }}>
              {signal.direction}
            </div>
            <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 5 }}>
              {styleLabel(signal.style)} · Created {new Date(signal.createdAt).toLocaleTimeString()}
            </div>
          </div>
          <ConfidenceRing score={score} size={80} label="confluence" />
        </div>

        {/* Badges */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <Badge
            label={signal.regime}
            color={signal.regime === 'TRENDING' ? colors.buyGreen : signal.regime === 'RANGING' ? colors.warning : colors.info}
          />
          {signal.killZoneActive && signal.killZoneName && (
            <Badge label={`⚡ ${signal.killZoneName} KZ`} color={colors.goldPrimary} />
          )}
          {signal.newsRisk && <Badge label="⚠ News Risk" color={colors.sellRed} />}
          {signal.htfConflict && <Badge label="⚔ HTF Conflict" color={colors.warning} />}
          <span style={{ marginLeft: 'auto', fontSize: 11, color: colors.textMuted }}>
            ⏱ {timeLeft(signal.expiresAt)} left
          </span>
        </div>
      </GlassCard>

      {/* Chart */}
      <GlassCard style={{ padding: '14px 12px 10px', marginBottom: 10 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: colors.textMuted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>
          Trade Setup
        </div>
        <SignalChart
          entry={signal.entry}
          sl={signal.sl}
          tp1={signal.tp1}
          tp2={signal.tp2}
          tp3={signal.tp3}
          direction={signal.direction}
          pair={signal.pair}
        />
      </GlassCard>

      {/* Price Levels */}
      <GlassCard style={{ padding: '4px 16px 4px', marginBottom: 10 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: colors.textMuted, padding: '10px 0 4px', textTransform: 'uppercase', letterSpacing: 0.5 }}>
          Levels
        </div>
        <PriceLevel
          label="Entry"
          value={fmt(signal.entry)}
          accentColor={colors.textPrimary}
        />
        <PriceLevel
          label="TP1 — 40% close"
          value={fmt(signal.tp1)}
          accentColor={colors.buyGreen}
          note="Move SL to breakeven at TP1"
          barWidth={40}
        />
        <PriceLevel
          label="TP2 — 30% close"
          value={fmt(signal.tp2)}
          accentColor='#4ADE80'
          note={`R:R 1:2 · Trail SL to TP1`}
          barWidth={70}
        />
        <PriceLevel
          label="TP3 — 30% hold"
          value={fmt(signal.tp3)}
          accentColor='#86EFAC'
          note="Full trail — aspirational target"
          barWidth={100}
        />
        <PriceLevel
          label="Stop Loss"
          value={fmt(signal.sl)}
          accentColor={colors.sellRed}
          note={`Invalidation · R:R 1:${signal.rr.toFixed(1)}`}
        />
      </GlassCard>

      {/* Module Analysis */}
      <GlassCard style={{ padding: 16, marginBottom: 10 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: colors.textPrimary, marginBottom: 14, letterSpacing: 0.2 }}>
          Module Analysis
        </div>
        {signal.modules.map(m => (
          <ModuleBar key={m.name} module={m} signalScore={signal.confluenceScore} />
        ))}
      </GlassCard>

      {/* Dissent warning */}
      {opposing.length > 0 && (
        <GlassCard style={{
          padding: 14, marginBottom: 10,
          border: `1px solid ${colors.warning}30`,
          background: 'rgba(245,158,11,0.05)',
        }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: colors.warning, marginBottom: 10 }}>
            ⚠ Dissenting Modules ({opposing.length})
          </div>
          {opposing.map(m => (
            <div key={m.name} style={{
              fontSize: 11, color: colors.textMuted, marginBottom: 6, lineHeight: 1.6,
              paddingLeft: 10,
              borderLeft: `2px solid ${colors.sellRed}40`,
            }}>
              <span style={{ color: colors.sellRed, fontWeight: 700 }}>{m.name}</span>
              {' '}
              <span style={{ color: colors.textMuted }}>
                ({m.weight}% weight) opposes this signal with score{' '}
                <span style={{ color: colors.warning, fontWeight: 600 }}>{m.score.toFixed(2)}</span>
              </span>
            </div>
          ))}
        </GlassCard>
      )}

      {/* Signal Decay */}
      <GlassCard style={{ padding: 14, marginBottom: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: colors.textSecondary }}>Signal Freshness</span>
          <span style={{ fontSize: 11, color: colors.textMuted }}>
            {timeLeft(signal.expiresAt)} remaining
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: 11, color: colors.textMuted }}>Base</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: colors.goldPrimary }}>
            {Math.round(signal.confluenceScore * 100)}%
          </span>
          <span style={{ fontSize: 11, color: colors.textMuted }}>→ Now</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: decayColor }}>
            {Math.round(score * 100)}%
          </span>
          <span style={{ fontSize: 10, color: colors.textMuted }}>
            ({Math.round(frac * 100)}% elapsed)
          </span>
        </div>
        {/* Decay bar */}
        <div style={{ height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 3, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${decayPct}%`,
            borderRadius: 3,
            background: `linear-gradient(90deg, ${decayColor}80, ${decayColor})`,
            transition: 'width 0.5s ease',
          }} />
        </div>
        {decayPct < 60 && (
          <div style={{ fontSize: 10, color: colors.warning, marginTop: 6 }}>
            Signal is fading — score below 60% of original confidence.
          </div>
        )}
      </GlassCard>

      {/* Execute button */}
      <button
        style={{
          width: '100%',
          padding: '16px 0',
          background: `linear-gradient(135deg, ${colors.goldPrimary}, ${colors.goldLight})`,
          border: 'none',
          borderRadius: 14,
          color: '#0A0A1A',
          fontSize: 15,
          fontWeight: 800,
          cursor: 'pointer',
          letterSpacing: 0.5,
          marginBottom: 8,
          boxShadow: `0 4px 20px rgba(212,168,67,0.35)`,
          transition: 'opacity 0.15s ease',
        }}
        onMouseEnter={e => (e.currentTarget.style.opacity = '0.9')}
        onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
      >
        Execute Paper Trade
      </button>

      <p style={{ fontSize: 10, color: colors.textMuted, textAlign: 'center', lineHeight: 1.6, marginBottom: 24 }}>
        Paper trading only. Simulated capital · No real money at risk.
        <br />Connect a broker account in Settings to trade live.
      </p>
    </div>
  );
}
