import React from 'react';
import { colors } from '../theme';

interface ConfidenceRingProps {
  score: number;
  size?: number;
  label?: string;
}

export function ConfidenceRing({ score, size = 64, label }: ConfidenceRingProps) {
  const pct = Math.round(score * 100);
  const r = (size / 2) - 6;
  const circ = 2 * Math.PI * r;
  const dash = circ * pct / 100;
  const ringColor = pct >= 80 ? colors.goldPrimary : pct >= 65 ? colors.goldLight : colors.warning;

  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={5}
        />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none"
          stroke={ringColor}
          strokeWidth={5}
          strokeDasharray={`${dash} ${circ - dash}`}
          strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 4px ${ringColor}80)` }}
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <span style={{ fontSize: size < 60 ? 11 : 14, fontWeight: 700, color: ringColor, lineHeight: 1 }}>
          {pct}%
        </span>
        {label && (
          <span style={{ fontSize: 9, color: colors.textMuted, marginTop: 1 }}>{label}</span>
        )}
      </div>
    </div>
  );
}
