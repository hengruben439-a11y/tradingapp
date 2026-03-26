import React, { useState, useEffect } from 'react';
import { colors } from '../theme';
import { GlassCard } from '../components/GlassCard';
import { mockCalendar } from '../services/mock';
import type { CalendarEvent } from '../types';

function formatTime(iso: string, tz = 'SGT'): string {
  const d = new Date(iso);
  return d.toLocaleTimeString('en-SG', { hour: '2-digit', minute: '2-digit', hour12: false }) + ' SGT';
}

function formatRelative(iso: string): string {
  const diff = new Date(iso).getTime() - Date.now();
  if (diff < 0) return 'Past';
  const m = Math.floor(diff / 60_000);
  if (m < 1) return 'Now!';
  if (m < 60) return `in ${m}m`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem > 0 ? `in ${h}h ${rem}m` : `in ${h}h`;
}

function impactColor(impact: CalendarEvent['impact']) {
  if (impact === 'high') return colors.sellRed;
  if (impact === 'medium') return colors.warning;
  return colors.textMuted;
}

function impactLabel(impact: CalendarEvent['impact']) {
  if (impact === 'high') return '🔴 High';
  if (impact === 'medium') return '🟡 Medium';
  return '⚪ Low';
}

function CountdownRing({ iso, size = 48 }: { iso: string; size?: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const diff = new Date(iso).getTime() - now;
  if (diff <= 0) return <span style={{ fontSize: 11, color: colors.sellRed, fontWeight: 700 }}>NOW</span>;
  const totalMins = 60;
  const mins = Math.floor(diff / 60_000);
  const pct = Math.max(0, Math.min(1, mins / totalMins));
  const r = size / 2 - 5;
  const circ = 2 * Math.PI * r;
  const color = mins < 15 ? colors.sellRed : mins < 30 ? colors.warning : colors.goldPrimary;

  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={4} />
        <circle
          cx={size/2} cy={size/2} r={r} fill="none"
          stroke={color} strokeWidth={4}
          strokeDasharray={`${circ * pct} ${circ * (1 - pct)}`}
          strokeLinecap="round"
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 9, fontWeight: 700, color,
      }}>
        {mins < 60 ? `${mins}m` : `${Math.floor(mins/60)}h`}
      </div>
    </div>
  );
}

function EventCard({ event }: { event: CalendarEvent }) {
  const [expanded, setExpanded] = useState(false);
  const high = event.impact === 'high';

  return (
    <GlassCard
      style={{
        padding: '12px 14px', marginBottom: 8,
        ...(high ? { borderColor: `${colors.sellRed}30` } : {}),
      }}
      onClick={() => setExpanded(e => !e)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <CountdownRing iso={event.time} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: colors.textPrimary }}>{event.title}</span>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: colors.textMuted }}>{formatTime(event.time)}</span>
            <span style={{ fontSize: 10, color: impactColor(event.impact), fontWeight: 600 }}>
              {impactLabel(event.impact)}
            </span>
            <span style={{ fontSize: 10, color: colors.info, fontWeight: 600 }}>{event.currency}</span>
          </div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 2 }}>Pairs affected</div>
          <div style={{ fontSize: 10, color: colors.goldPrimary, fontWeight: 600 }}>
            {event.pairs.join(' · ')}
          </div>
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid rgba(255,255,255,0.06)` }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
            <DataPoint label="Forecast" value={event.forecast ?? '—'} />
            <DataPoint label="Previous" value={event.previous ?? '—'} />
            <DataPoint label="Actual" value={event.actual ?? 'Pending'} highlight={!!event.actual} />
          </div>
          {high && (
            <div style={{
              marginTop: 10, padding: '8px 10px',
              background: `${colors.sellRed}10`,
              borderRadius: 6, fontSize: 11, color: colors.warning, lineHeight: 1.5,
            }}>
              ⚠ Signal suppression active 15min before and 5min after this event.
            </div>
          )}
        </div>
      )}
    </GlassCard>
  );
}

function DataPoint({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 6, padding: '8px 10px' }}>
      <div style={{ fontSize: 10, color: colors.textMuted }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: highlight ? colors.buyGreen : colors.textPrimary }}>
        {value}
      </div>
    </div>
  );
}

export function Calendar() {
  const [filter, setFilter] = useState<'all' | 'high'>('high');
  const events = mockCalendar.filter(e => filter === 'all' || e.impact === 'high');
  const upcoming = events.filter(e => new Date(e.time) > new Date());

  return (
    <div>
      {/* Suppression banner */}
      {mockCalendar.some(e => {
        const diff = Math.abs(new Date(e.time).getTime() - Date.now());
        return e.impact === 'high' && diff < 15 * 60_000;
      }) && (
        <div style={{
          padding: '10px 14px', marginBottom: 12, borderRadius: 10,
          background: `${colors.sellRed}15`,
          border: `1px solid ${colors.sellRed}30`,
          fontSize: 12, color: colors.sellRed, fontWeight: 600,
        }}>
          🚫 Signals suppressed — high-impact news event imminent
        </div>
      )}

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
        <GlassCard style={{ padding: '10px 12px' }}>
          <div style={{ fontSize: 10, color: colors.textMuted }}>Today's Events</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: colors.textPrimary }}>{events.length}</div>
        </GlassCard>
        <GlassCard style={{ padding: '10px 12px' }}>
          <div style={{ fontSize: 10, color: colors.textMuted }}>High Impact</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: colors.sellRed }}>
            {events.filter(e => e.impact === 'high').length}
          </div>
        </GlassCard>
      </div>

      {/* Filter pills */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        {(['high', 'all'] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: '6px 14px', borderRadius: 20, border: 'none',
              background: filter === f ? colors.goldPrimary : 'rgba(255,255,255,0.08)',
              color: filter === f ? colors.backgroundDeep : colors.textSecondary,
              fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}
          >
            {f === 'high' ? 'High Impact' : 'All Events'}
          </button>
        ))}
      </div>

      {upcoming.length === 0 ? (
        <GlassCard style={{ padding: 32, textAlign: 'center' }}>
          <div style={{ fontSize: 14, color: colors.textSecondary }}>No upcoming events</div>
        </GlassCard>
      ) : (
        upcoming.map(event => <EventCard key={event.id} event={event} />)
      )}
    </div>
  );
}
