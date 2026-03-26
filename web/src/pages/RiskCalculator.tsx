import React, { useState } from 'react';
import { colors } from '../theme';
import { GlassCard } from '../components/GlassCard';

type Pair = 'XAUUSD' | 'GBPJPY';

export function RiskCalculator() {
  const [balance, setBalance] = useState(10000);
  const [riskPct, setRiskPct] = useState(1.0);
  const [pair, setPair] = useState<Pair>('XAUUSD');
  const [slPips, setSlPips] = useState(pair === 'XAUUSD' ? 14.5 : 54);

  const pipValue = pair === 'XAUUSD' ? 1.0 : 9.50;
  const dollarRisk = balance * (riskPct / 100);
  const lotSize = slPips > 0 ? dollarRisk / (slPips * pipValue) : 0;
  const margin = pair === 'XAUUSD' ? lotSize * 3312 * 0.02 : lotSize * 100_000 / 100 * 1.27;

  return (
    <div>
      <GlassCard style={{ padding: 20, marginBottom: 12 }}>
        <h2 style={{ fontSize: 17, fontWeight: 700, color: colors.textPrimary, marginBottom: 18 }}>
          Risk Calculator
        </h2>

        {/* Pair select */}
        <div style={{ marginBottom: 18 }}>
          <label style={{ fontSize: 12, color: colors.textSecondary, display: 'block', marginBottom: 8 }}>
            Trading Pair
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            {(['XAUUSD', 'GBPJPY'] as Pair[]).map(p => (
              <button
                key={p}
                onClick={() => {
                  setPair(p);
                  setSlPips(p === 'XAUUSD' ? 14.5 : 54);
                }}
                style={{
                  flex: 1, padding: '10px',
                  borderRadius: 10, border: 'none',
                  background: pair === p ? colors.goldPrimary : 'rgba(255,255,255,0.08)',
                  color: pair === p ? colors.backgroundDeep : colors.textSecondary,
                  fontSize: 13, fontWeight: 700, cursor: 'pointer',
                }}
              >
                {p === 'XAUUSD' ? '🥇 XAUUSD' : '🇬🇧 GBPJPY'}
              </button>
            ))}
          </div>
        </div>

        {/* Balance */}
        <SliderInput
          label="Account Balance"
          value={balance}
          min={1000} max={100_000} step={500}
          display={`$${balance.toLocaleString()}`}
          onChange={setBalance}
        />

        {/* Risk % */}
        <SliderInput
          label="Risk Per Trade"
          value={riskPct}
          min={0.5} max={5} step={0.5}
          display={`${riskPct.toFixed(1)}%`}
          onChange={setRiskPct}
          color={riskPct > 2 ? colors.warning : colors.goldPrimary}
        />

        {/* SL distance */}
        <SliderInput
          label={`Stop Loss Distance (${pair === 'XAUUSD' ? 'price points' : 'pips'})`}
          value={slPips}
          min={pair === 'XAUUSD' ? 5 : 15}
          max={pair === 'XAUUSD' ? 50 : 150}
          step={pair === 'XAUUSD' ? 0.5 : 1}
          display={`${slPips} ${pair === 'XAUUSD' ? 'pts' : 'pips'}`}
          onChange={setSlPips}
        />
      </GlassCard>

      {/* Results */}
      <GlassCard style={{ padding: 20 }} highlighted>
        <div style={{ fontSize: 13, fontWeight: 700, color: colors.textSecondary, marginBottom: 16 }}>
          Position Sizing
        </div>

        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 4 }}>Lot Size</div>
          <div style={{ fontSize: 48, fontWeight: 900, color: colors.goldPrimary, lineHeight: 1 }}>
            {lotSize.toFixed(2)}
          </div>
          <div style={{ fontSize: 12, color: colors.textSecondary }}>Standard Lots</div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
          <ResultBox label="Dollar Risk" value={`$${dollarRisk.toFixed(2)}`} color={colors.sellRed} />
          <ResultBox label="Pip Value" value={`$${pipValue.toFixed(2)}`} color={colors.textSecondary} />
          <ResultBox label="Est. Margin" value={`$${margin.toFixed(0)}`} color={colors.warning} />
        </div>

        <div style={{ marginTop: 14, padding: '10px 12px', background: 'rgba(212,168,67,0.06)', borderRadius: 8, fontSize: 12, color: colors.textSecondary, lineHeight: 1.6 }}>
          Risking <span style={{ color: colors.sellRed, fontWeight: 600 }}>{riskPct}% = ${dollarRisk.toFixed(2)}</span>
          {' '}on {pair} with a <span style={{ fontWeight: 600 }}>{slPips} {pair === 'XAUUSD' ? 'pt' : 'pip'} SL</span>
          {' '}→ <span style={{ color: colors.goldPrimary, fontWeight: 700 }}>{lotSize.toFixed(2)} lots</span>
        </div>

        {riskPct > 2 && (
          <div style={{ marginTop: 10, padding: '8px 10px', background: `${colors.warning}10`, borderRadius: 6, fontSize: 11, color: colors.warning }}>
            ⚠ Risking over 2% per trade is above recommended levels. Keep risk between 1-2% for capital preservation.
          </div>
        )}
      </GlassCard>
    </div>
  );
}

function SliderInput({
  label, value, min, max, step, display, onChange, color,
}: {
  label: string; value: number; min: number; max: number; step: number;
  display: string; onChange: (v: number) => void; color?: string;
}) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <label style={{ fontSize: 12, color: colors.textSecondary }}>{label}</label>
        <span style={{ fontSize: 14, fontWeight: 700, color: color ?? colors.goldPrimary }}>{display}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        style={{
          width: '100%', appearance: 'none', WebkitAppearance: 'none',
          height: 4, background: `linear-gradient(to right, ${color ?? colors.goldPrimary} ${((value - min) / (max - min)) * 100}%, rgba(255,255,255,0.1) 0)`,
          borderRadius: 2, outline: 'none', cursor: 'pointer',
        }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
        <span style={{ fontSize: 10, color: colors.textMuted }}>{min}</span>
        <span style={{ fontSize: 10, color: colors.textMuted }}>{max}</span>
      </div>
    </div>
  );
}

function ResultBox({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 8, padding: '10px 10px', textAlign: 'center' }}>
      <div style={{ fontSize: 10, color: colors.textMuted, marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}
