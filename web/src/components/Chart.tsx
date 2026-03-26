import React, { useMemo, useState, useEffect, useRef } from 'react';

// ---------------------------------------------------------------------------
// MiniChart — sparkline for signal cards
// ---------------------------------------------------------------------------

interface MiniChartProps {
  prices: number[];
  direction: 'BUY' | 'SELL';
  width?: number;
  height?: number;
}

export function MiniChart({ prices, direction, width = 120, height = 40 }: MiniChartProps) {
  const color = direction === 'BUY' ? '#22C55E' : '#EF4444';
  const gradId = `mini-grad-${direction}-${width}`;

  const { points, closedPath } = useMemo(() => {
    if (prices.length < 2) return { points: '', closedPath: '' };
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;
    const pts = prices.map((p, i) => {
      const x = (i / (prices.length - 1)) * width;
      const y = height - ((p - min) / range) * (height - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    return {
      points: pts.join(' '),
      closedPath: `M ${pts[0]} L ${pts.join(' L ')} L ${width},${height} L 0,${height} Z`,
    };
  }, [prices, width, height]);

  return (
    <svg width={width} height={height} style={{ display: 'block', overflow: 'visible' }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {closedPath && <path d={closedPath} fill={`url(#${gradId})`} />}
      {points && (
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// SignalChart — live candlestick chart for SignalDetail
// ---------------------------------------------------------------------------

interface OHLCV {
  open: number;
  high: number;
  low: number;
  close: number;
}

export type ChartTimeframe = '1m' | '5m' | '15m' | '30m' | '4H';

const TF_CANDLE_COUNT: Record<ChartTimeframe, number> = {
  '1m': 40,
  '5m': 40,
  '15m': 36,
  '30m': 32,
  '4H': 28,
};

// Each timeframe ticks at a different interval (ms) to feel realistic
const TF_TICK_MS: Record<ChartTimeframe, number> = {
  '1m': 2000,
  '5m': 4000,
  '15m': 5000,
  '30m': 6000,
  '4H': 8000,
};

interface SignalChartProps {
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  tp3: number;
  direction: 'BUY' | 'SELL';
  pair: string;
  defaultTf?: ChartTimeframe;
}

function buildCandles(entry: number, sl: number, tp1: number, direction: 'BUY' | 'SELL', count: number): OHLCV[] {
  const range = Math.abs(tp1 - sl);
  const volatility = range * 0.10;
  const trend = direction === 'BUY' ? 1 : -1;
  const start = direction === 'BUY' ? sl + range * 0.15 : tp1 + range * 0.15;

  const candles: OHLCV[] = [];
  let price = start;

  for (let i = 0; i < count; i++) {
    const progress = i / count;
    const trendBias = progress * trend * range * 0.65;
    const noise = (Math.random() - 0.47) * volatility;
    const close = start + trendBias + noise;
    const bodyRange = volatility * (0.25 + Math.random() * 0.5);
    const open = price;
    const high = Math.max(open, close) + Math.random() * bodyRange * 0.5;
    const low = Math.min(open, close) - Math.random() * bodyRange * 0.5;
    candles.push({ open, high, low, close });
    price = close;
  }
  return candles;
}

export function SignalChart({ entry, sl, tp1, tp2, tp3, direction, pair, defaultTf = '15m' }: SignalChartProps) {
  const isXau = pair.startsWith('XAU');
  const fmt = (n: number) => isXau ? n.toFixed(2) : n.toFixed(3);

  const [tf, setTf] = useState<ChartTimeframe>(defaultTf);

  // Canvas dimensions
  const svgW = 420;
  const svgH = 240;
  const padL = 10;
  const padR = 80;
  const padT = 16;
  const padB = 16;
  const chartW = svgW - padL - padR;
  const chartH = svgH - padT - padB;

  const candleCount = TF_CANDLE_COUNT[tf];

  // Seed candles on mount and when tf/signal changes
  const [candles, setCandles] = useState<OHLCV[]>(() =>
    buildCandles(entry, sl, tp1, direction, candleCount)
  );

  const prevKey = useRef(`${entry}-${tf}`);
  useEffect(() => {
    const key = `${entry}-${tf}`;
    if (prevKey.current !== key) {
      prevKey.current = key;
      setCandles(buildCandles(entry, sl, tp1, direction, candleCount));
    }
  }, [entry, sl, tp1, direction, tf, candleCount]);

  // Live tick — speed varies by timeframe
  useEffect(() => {
    const tickMs = TF_TICK_MS[tf];
    const id = setInterval(() => {
      setCandles(prev => {
        const last = prev[prev.length - 1];
        const range = Math.abs(tp1 - sl);
        const volatility = range * 0.06;
        const trend = direction === 'BUY' ? 1 : -1;
        const drift = (Math.random() - 0.47) * volatility + trend * volatility * 0.1;
        const open = last.close;
        const close = open + drift;
        const high = Math.max(open, close) + Math.random() * volatility * 0.3;
        const low = Math.min(open, close) - Math.random() * volatility * 0.3;
        return [...prev.slice(1), { open, high, low, close }];
      });
    }, tickMs);
    return () => clearInterval(id);
  }, [entry, sl, tp1, direction, tf]);

  // Price range — include all key levels with generous padding
  const allPrices = [sl, entry, tp1, tp2, tp3, ...candles.map(c => c.high), ...candles.map(c => c.low)];
  const priceMin = Math.min(...allPrices) - Math.abs(tp1 - sl) * 0.10;
  const priceMax = Math.max(...allPrices) + Math.abs(tp1 - sl) * 0.10;
  const priceRange = priceMax - priceMin || 1;

  const toY = (price: number) =>
    padT + chartH - ((price - priceMin) / priceRange) * chartH;

  const candleW = (chartW / candles.length) * 0.6;
  const step = chartW / candles.length;

  const isBuyDir = direction === 'BUY';
  const levels = [
    { price: tp3, color: '#22C55E', opacity: 0.45, label: 'TP3', dash: '3,4' },
    { price: tp2, color: '#22C55E', opacity: 0.65, label: 'TP2', dash: '3,3' },
    { price: tp1, color: '#22C55E', opacity: 0.90, label: 'TP1', dash: '4,3' },
    { price: entry, color: '#E8C874', opacity: 1.0,  label: 'Entry', dash: '6,3' },
    { price: sl,    color: '#EF4444', opacity: 0.90, label: 'SL',    dash: '4,3' },
  ];

  // Horizontal price gridlines at 4 evenly spaced levels
  const gridPrices = Array.from({ length: 4 }, (_, i) =>
    priceMin + (priceRange / 3) * i
  );

  const TF_OPTIONS: ChartTimeframe[] = ['1m', '5m', '15m', '30m', '4H'];

  return (
    <div>
      {/* Timeframe selector */}
      <div style={{
        display: 'flex', gap: 4, marginBottom: 8,
        flexWrap: 'wrap',
      }}>
        {TF_OPTIONS.map(t => (
          <button
            key={t}
            onClick={() => setTf(t)}
            style={{
              fontSize: 11, fontWeight: 600,
              padding: '4px 10px', borderRadius: 6, cursor: 'pointer',
              border: '1px solid',
              borderColor: tf === t ? 'rgba(212,168,67,0.6)' : 'rgba(255,255,255,0.12)',
              background: tf === t ? 'rgba(212,168,67,0.15)' : 'rgba(255,255,255,0.04)',
              color: tf === t ? '#D4A843' : '#9CA3AF',
              transition: 'all 0.15s ease',
            }}
          >
            {t}
          </button>
        ))}
        <span style={{
          marginLeft: 'auto', fontSize: 10, color: '#9CA3AF',
          alignSelf: 'center', fontStyle: 'italic',
        }}>
          live sim
        </span>
      </div>

    <svg
      width="100%"
      viewBox={`0 0 ${svgW} ${svgH}`}
      style={{ display: 'block', overflow: 'visible' }}
    >
      {/* Grid lines */}
      {gridPrices.map((gp, i) => (
        <line
          key={i}
          x1={padL} y1={toY(gp)}
          x2={padL + chartW} y2={toY(gp)}
          stroke="rgba(255,255,255,0.05)"
          strokeWidth={1}
        />
      ))}

      {/* Candles */}
      {candles.map((c, i) => {
        const cx = padL + i * step + (step - candleW) / 2;
        const bull = c.close >= c.open;
        const bodyTop = toY(Math.max(c.open, c.close));
        const bodyBot = toY(Math.min(c.open, c.close));
        const bodyH = Math.max(bodyBot - bodyTop, 1.5);
        const col = bull ? '#22C55E' : '#EF4444';
        const wickX = cx + candleW / 2;
        const isLast = i === candles.length - 1;
        return (
          <g key={i}>
            <line
              x1={wickX} y1={toY(c.high)}
              x2={wickX} y2={toY(c.low)}
              stroke={col} strokeWidth={isLast ? 1.2 : 0.9}
              opacity={isLast ? 1 : 0.7}
            />
            <rect
              x={cx} y={bodyTop}
              width={candleW} height={bodyH}
              fill={bull ? col : 'none'}
              stroke={col} strokeWidth={bull ? 0 : 1}
              opacity={isLast ? 1 : 0.8}
              rx={0.5}
            />
          </g>
        );
      })}

      {/* Zone fill between Entry and SL */}
      <rect
        x={padL}
        y={isBuyDir ? toY(entry) : toY(sl)}
        width={chartW}
        height={Math.abs(toY(entry) - toY(sl))}
        fill="rgba(239,68,68,0.06)"
      />

      {/* Level lines with labels */}
      {levels.map(({ price, color, opacity, label, dash }) => {
        const y = toY(price);
        return (
          <g key={label}>
            <line
              x1={padL} y1={y}
              x2={padL + chartW + 4} y2={y}
              stroke={color} strokeWidth={label === 'Entry' ? 1.5 : 1}
              strokeDasharray={dash} opacity={opacity}
            />
            {/* Right-side label */}
            <rect
              x={padL + chartW + 6} y={y - 8}
              width={72} height={16}
              fill="rgba(10,10,26,0.7)" rx={3}
            />
            <text
              x={padL + chartW + 10} y={y + 1}
              fontSize={9} fontWeight={700}
              fill={color} opacity={opacity}
              fontFamily="'SF Mono','Fira Code',monospace"
              dominantBaseline="middle"
            >
              {label}
            </text>
            <text
              x={padL + chartW + 42} y={y + 1}
              fontSize={8}
              fill={color} opacity={opacity * 0.8}
              fontFamily="'SF Mono','Fira Code',monospace"
              dominantBaseline="middle"
            >
              {fmt(price)}
            </text>
          </g>
        );
      })}

      {/* Current price indicator on last candle */}
      {(() => {
        const last = candles[candles.length - 1];
        const y = toY(last.close);
        const col = last.close >= last.open ? '#22C55E' : '#EF4444';
        return (
          <g>
            <circle cx={padL + chartW - 2} cy={y} r={3} fill={col} opacity={0.9} />
            <line
              x1={padL + chartW - 2} y1={y}
              x2={padL + chartW + 4} y2={y}
              stroke={col} strokeWidth={1} opacity={0.5}
            />
          </g>
        );
      })()}
    </svg>
    </div>
  );
}
