import React, { useState } from 'react';
import { colors } from '../theme';
import { GlassCard } from '../components/GlassCard';
import { mockJournal } from '../services/mock';
import type { JournalEntry } from '../types';

const winRate = () => {
  const closed = mockJournal.filter(j => j.outcome);
  const wins = closed.filter(j => j.outcome !== 'sl');
  return closed.length > 0 ? Math.round((wins.length / closed.length) * 100) : 0;
};

const totalPnl = () =>
  mockJournal.reduce((sum, j) => sum + (j.pnlUsd ?? 0), 0);

const profitFactor = () => {
  const wins = mockJournal.filter(j => (j.pnlUsd ?? 0) > 0).reduce((s, j) => s + (j.pnlUsd ?? 0), 0);
  const losses = Math.abs(mockJournal.filter(j => (j.pnlUsd ?? 0) < 0).reduce((s, j) => s + (j.pnlUsd ?? 0), 0));
  return losses > 0 ? (wins / losses).toFixed(2) : '∞';
};

function outcomeLabel(outcome?: JournalEntry['outcome']) {
  switch (outcome) {
    case 'tp1': return { label: 'TP1 ✓', color: colors.buyGreen };
    case 'tp2': return { label: 'TP2 ✓✓', color: colors.buyGreen };
    case 'tp3': return { label: 'TP3 ✓✓✓', color: colors.goldPrimary };
    case 'sl': return { label: 'SL ✗', color: colors.sellRed };
    case 'manual': return { label: 'Manual', color: colors.warning };
    default: return { label: 'Open', color: colors.info };
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-SG', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function EntryCard({ entry }: { entry: JournalEntry }) {
  const [expanded, setExpanded] = useState(false);
  const outcome = outcomeLabel(entry.outcome);
  const pnlPos = (entry.pnlUsd ?? 0) >= 0;
  const fmt = (n: number) => entry.pair === 'XAUUSDB' ? n.toFixed(2) : n.toFixed(3);

  return (
    <GlassCard style={{ padding: 14, marginBottom: 8 }} onClick={() => setExpanded(e => !e)}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
            <span style={{ fontSize: 16 }}>{entry.pair === 'XAUUSDB' ? '🥇' : '🇬🇧'}</span>
            <span style={{ fontSize: 14, fontWeight: 700, color: colors.textPrimary }}>{entry.pair}</span>
            <span style={{
              fontSize: 11, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
              color: entry.direction === 'BUY' ? colors.buyGreen : colors.sellRed,
              background: entry.direction === 'BUY' ? colors.buyGreenAlpha : colors.sellRedAlpha,
            }}>
              {entry.direction}
            </span>
          </div>
          <div style={{ fontSize: 11, color: colors.textMuted }}>{formatDate(entry.openedAt)}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: pnlPos ? colors.buyGreen : colors.sellRed }}>
            {pnlPos ? '+' : ''}${entry.pnlUsd?.toFixed(2) ?? '—'}
          </div>
          <span style={{
            fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
            background: `${outcome.color}15`, color: outcome.color,
          }}>
            {outcome.label}
          </span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
        <MiniStat label="Entry" value={fmt(entry.entry)} />
        <MiniStat label="Exit" value={entry.exitPrice ? fmt(entry.exitPrice) : '—'} />
        <MiniStat label="R:R" value={entry.rrAchieved ? `${entry.rrAchieved.toFixed(2)}x` : '—'} color={pnlPos ? colors.buyGreen : colors.sellRed} />
      </div>

      {expanded && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid rgba(255,255,255,0.06)` }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 10 }}>
            <MiniStat label="Confluence" value={`${Math.round(entry.confluenceScore * 100)}%`} color={colors.goldPrimary} />
            <MiniStat label="P&L (pips)" value={`${entry.pnlPips ?? '—'}`} color={pnlPos ? colors.buyGreen : colors.sellRed} />
            <MiniStat label="Duration" value={entry.holdDuration ? `${entry.holdDuration}m` : '—'} />
            <MiniStat label="Mode" value={entry.isPaper ? 'Paper' : 'Live'} color={entry.isPaper ? colors.warning : colors.buyGreen} />
          </div>

          {entry.postMortem && (
            <div style={{
              padding: '10px 12px',
              background: `${colors.sellRed}08`,
              border: `1px solid ${colors.sellRed}20`,
              borderRadius: 8,
            }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: colors.sellRed, marginBottom: 6 }}>
                📋 Post-Mortem
              </div>
              <p style={{ fontSize: 11, color: colors.textSecondary, lineHeight: 1.6 }}>
                {entry.postMortem}
              </p>
            </div>
          )}
        </div>
      )}
    </GlassCard>
  );
}

function MiniStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 6, padding: '6px 8px' }}>
      <div style={{ fontSize: 9, color: colors.textMuted }}>{label}</div>
      <div style={{ fontSize: 12, fontWeight: 600, color: color ?? colors.textPrimary }}>{value}</div>
    </div>
  );
}

// Simple equity curve SVG
function EquityCurve() {
  const balances = [10000, 10187.5, 10092.5, 10422.5, 10532.5];
  const min = Math.min(...balances);
  const max = Math.max(...balances);
  const range = max - min || 1;
  const w = 280, h = 60;
  const pts = balances.map((b, i) => {
    const x = (i / (balances.length - 1)) * w;
    const y = h - ((b - min) / range) * (h - 10) - 5;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <defs>
        <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={colors.goldPrimary} stopOpacity="0.3" />
          <stop offset="100%" stopColor={colors.goldPrimary} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <polygon
        points={`0,${h} ${pts} ${w},${h}`}
        fill="url(#eq)"
      />
      <polyline
        points={pts}
        fill="none"
        stroke={colors.goldPrimary}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Journal() {
  const pnl = totalPnl();
  const pnlPos = pnl >= 0;

  return (
    <div>
      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
        <GlassCard style={{ padding: '12px 14px' }}>
          <div style={{ fontSize: 10, color: colors.textMuted, marginBottom: 2 }}>Total P&L</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: pnlPos ? colors.buyGreen : colors.sellRed }}>
            {pnlPos ? '+' : ''}${pnl.toFixed(2)}
          </div>
        </GlassCard>
        <GlassCard style={{ padding: '12px 14px' }}>
          <div style={{ fontSize: 10, color: colors.textMuted, marginBottom: 2 }}>Win Rate</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: colors.goldPrimary }}>
            {winRate()}%
          </div>
        </GlassCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
        <GlassCard style={{ padding: '10px 12px' }}>
          <div style={{ fontSize: 10, color: colors.textMuted }}>Profit Factor</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: colors.textPrimary }}>{profitFactor()}</div>
        </GlassCard>
        <GlassCard style={{ padding: '10px 12px' }}>
          <div style={{ fontSize: 10, color: colors.textMuted }}>Trades</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: colors.textPrimary }}>{mockJournal.length}</div>
        </GlassCard>
      </div>

      {/* Equity curve */}
      <GlassCard style={{ padding: '14px 16px', marginBottom: 14 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: colors.textSecondary, marginBottom: 10 }}>
          Equity Curve
        </div>
        <EquityCurve />
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
          <span style={{ fontSize: 10, color: colors.textMuted }}>$10,000</span>
          <span style={{ fontSize: 10, color: colors.goldPrimary, fontWeight: 600 }}>$10,532.50</span>
        </div>
      </GlassCard>

      {/* Trade list */}
      <div style={{ fontSize: 13, fontWeight: 600, color: colors.textSecondary, marginBottom: 10 }}>
        Trade History
      </div>
      {mockJournal.map(entry => (
        <EntryCard key={entry.id} entry={entry} />
      ))}
    </div>
  );
}
