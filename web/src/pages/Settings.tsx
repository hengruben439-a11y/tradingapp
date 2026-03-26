import React, { useState } from 'react';
import { colors } from '../theme';
import { GlassCard } from '../components/GlassCard';
import { mockUser } from '../services/mock';
import type { UIMode, TradingStyle } from '../types';

const MODES: { key: UIMode; label: string; desc: string; gate: string }[] = [
  { key: 'simple', label: 'Simple', desc: 'Top signals, direction + TP/SL, plain-English confidence', gate: 'All tiers' },
  { key: 'pro', label: 'Pro', desc: 'Full signals, module dissent bars, regime badge, all analytics', gate: 'Premium +' },
  { key: 'max', label: 'Max', desc: 'Raw scores, decay timer, advanced analytics, CSV export', gate: 'Pro only' },
];

const STYLES: { key: TradingStyle; label: string; entry: string; hold: string }[] = [
  { key: 'scalping', label: 'Scalping', entry: '1m / 5m', hold: '1–30 min' },
  { key: 'day_trading', label: 'Day Trading', entry: '15m / 30m', hold: '1–8 hours' },
  { key: 'swing_trading', label: 'Swing', entry: '1H / 4H', hold: '1–14 days' },
  { key: 'position_trading', label: 'Position', entry: '1D', hold: '2–12 weeks' },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: colors.textMuted, letterSpacing: 0.8, textTransform: 'uppercase', marginBottom: 8, paddingLeft: 4 }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function ToggleRow({ label, desc, value, onChange }: {
  label: string; desc?: string; value: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '12px 0', borderBottom: `1px solid rgba(255,255,255,0.05)`,
    }}>
      <div>
        <div style={{ fontSize: 14, color: colors.textPrimary }}>{label}</div>
        {desc && <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>{desc}</div>}
      </div>
      <button
        onClick={() => onChange(!value)}
        style={{
          width: 44, height: 24, borderRadius: 12, border: 'none', cursor: 'pointer',
          background: value ? colors.goldPrimary : 'rgba(255,255,255,0.1)',
          position: 'relative', transition: 'background 0.2s ease', flexShrink: 0,
        }}
      >
        <span style={{
          position: 'absolute', top: 2, width: 20, height: 20,
          borderRadius: '50%', background: '#fff',
          left: value ? 22 : 2,
          transition: 'left 0.2s ease',
          boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
        }} />
      </button>
    </div>
  );
}

export function Settings() {
  const [uiMode, setUiMode] = useState<UIMode>(mockUser.uiMode);
  const [style, setStyle] = useState<TradingStyle>(mockUser.tradingStyle);
  const [pushAlerts, setPushAlerts] = useState(true);
  const [telegramAlerts, setTelegramAlerts] = useState(true);
  const [newsAlerts, setNewsAlerts] = useState(true);
  const [dailyRundown, setDailyRundown] = useState(true);
  const [tz, setTz] = useState('SGT');

  const tierBadgeColor = mockUser.subscriptionTier === 'pro' ? colors.goldPrimary
    : mockUser.subscriptionTier === 'premium' ? colors.goldLight : colors.textMuted;

  return (
    <div>
      {/* Profile card */}
      <GlassCard style={{ padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 44, height: 44, borderRadius: '50%',
            background: `linear-gradient(135deg, ${colors.goldPrimary}, ${colors.ambientGradientStart})`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 18, fontWeight: 700, color: colors.backgroundDeep,
          }}>
            T
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: colors.textPrimary }}>
              {mockUser.email}
            </div>
            <div style={{ display: 'flex', gap: 6, marginTop: 3 }}>
              <span style={{
                fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
                background: `${tierBadgeColor}20`, color: tierBadgeColor,
                textTransform: 'uppercase', letterSpacing: 0.5,
              }}>
                {mockUser.subscriptionTier}
              </span>
              <span style={{ fontSize: 10, color: colors.textMuted, alignSelf: 'center' }}>
                Paper: ${mockUser.paperBalance.toLocaleString()}
              </span>
            </div>
          </div>
        </div>
      </GlassCard>

      {/* UI Mode */}
      <Section title="UI Complexity Mode">
        <GlassCard style={{ padding: '8px 12px' }}>
          {MODES.map(m => {
            const locked = (m.key === 'pro' && mockUser.subscriptionTier === 'free') ||
              (m.key === 'max' && mockUser.subscriptionTier !== 'pro');
            return (
              <div
                key={m.key}
                onClick={() => !locked && setUiMode(m.key)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 0', borderBottom: `1px solid rgba(255,255,255,0.05)`,
                  cursor: locked ? 'not-allowed' : 'pointer',
                  opacity: locked ? 0.5 : 1,
                }}
              >
                <div style={{
                  width: 18, height: 18, borderRadius: '50%', border: `2px solid ${uiMode === m.key ? colors.goldPrimary : 'rgba(255,255,255,0.2)'}`,
                  background: uiMode === m.key ? colors.goldPrimary : 'transparent',
                  flexShrink: 0,
                }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: colors.textPrimary }}>{m.label}</div>
                  <div style={{ fontSize: 11, color: colors.textMuted }}>{m.desc}</div>
                </div>
                <span style={{ fontSize: 10, color: colors.textMuted }}>{m.gate}</span>
              </div>
            );
          })}
        </GlassCard>
      </Section>

      {/* Trading Style */}
      <Section title="Trading Style">
        <GlassCard style={{ padding: '8px 12px' }}>
          {STYLES.map(s => (
            <div
              key={s.key}
              onClick={() => setStyle(s.key)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 0', borderBottom: `1px solid rgba(255,255,255,0.05)`,
                cursor: 'pointer',
              }}
            >
              <div style={{
                width: 18, height: 18, borderRadius: '50%',
                border: `2px solid ${style === s.key ? colors.goldPrimary : 'rgba(255,255,255,0.2)'}`,
                background: style === s.key ? colors.goldPrimary : 'transparent',
                flexShrink: 0,
              }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: colors.textPrimary }}>{s.label}</div>
                <div style={{ fontSize: 11, color: colors.textMuted }}>Entry: {s.entry} · Hold: {s.hold}</div>
              </div>
            </div>
          ))}
        </GlassCard>
      </Section>

      {/* Timezone */}
      <Section title="Timezone">
        <GlassCard style={{ padding: 12 }}>
          <div style={{ display: 'flex', gap: 6 }}>
            {['SGT', 'EST', 'GMT'].map(t => (
              <button
                key={t}
                onClick={() => setTz(t)}
                style={{
                  flex: 1, padding: '8px', borderRadius: 8, border: 'none',
                  background: tz === t ? colors.goldPrimary : 'rgba(255,255,255,0.08)',
                  color: tz === t ? colors.backgroundDeep : colors.textSecondary,
                  fontSize: 12, fontWeight: 600, cursor: 'pointer',
                }}
              >
                {t}
              </button>
            ))}
          </div>
        </GlassCard>
      </Section>

      {/* Notifications */}
      <Section title="Notifications">
        <GlassCard style={{ padding: '4px 16px' }}>
          <ToggleRow label="Push Alerts" desc="New signals, TP/SL hits" value={pushAlerts} onChange={setPushAlerts} />
          <ToggleRow label="Telegram Alerts" desc="Signal broadcasts via bot" value={telegramAlerts} onChange={setTelegramAlerts} />
          <ToggleRow label="News Alerts" desc="Countdown before high-impact events" value={newsAlerts} onChange={setNewsAlerts} />
          <ToggleRow label="Daily Rundown" desc="6:00 AM SGT market summary" value={dailyRundown} onChange={setDailyRundown} />
        </GlassCard>
      </Section>

      {/* Broker */}
      <Section title="Broker Connection">
        <GlassCard style={{ padding: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: 14, color: colors.textPrimary, fontWeight: 600 }}>HFM MT4/MT5</div>
              <div style={{ fontSize: 11, color: colors.textMuted }}>via MetaApi</div>
            </div>
            <button style={{
              padding: '8px 14px', borderRadius: 8, border: `1px solid ${colors.goldBorder}`,
              background: 'rgba(212,168,67,0.1)', color: colors.goldPrimary,
              fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}>
              Connect
            </button>
          </div>
        </GlassCard>
      </Section>

      {/* Subscription */}
      <Section title="Subscription">
        <GlassCard style={{ padding: 14 }} highlighted={mockUser.subscriptionTier !== 'pro'}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 700, color: tierBadgeColor, textTransform: 'capitalize' }}>
                {mockUser.subscriptionTier} Plan
              </div>
              <div style={{ fontSize: 11, color: colors.textMuted }}>
                {mockUser.subscriptionTier === 'pro' ? '$99/month · Auto-renews' : 'Upgrade for full access'}
              </div>
            </div>
            {mockUser.subscriptionTier !== 'pro' && (
              <button style={{
                padding: '8px 14px', borderRadius: 8, border: 'none',
                background: colors.goldPrimary, color: colors.backgroundDeep,
                fontSize: 12, fontWeight: 700, cursor: 'pointer',
              }}>
                Upgrade
              </button>
            )}
          </div>
        </GlassCard>
      </Section>

      <p style={{ fontSize: 10, color: colors.textMuted, textAlign: 'center', paddingBottom: 8, lineHeight: 1.6 }}>
        Trading involves substantial risk of loss. made. provides algorithmic analysis for educational purposes only. v1.0.0
      </p>
    </div>
  );
}
