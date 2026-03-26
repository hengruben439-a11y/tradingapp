import React, { useState, useEffect } from 'react';
import { LIVE_PRICES } from '../services/mock';
import { colors } from '../theme';

interface TickerPrice {
  bid: number;
  ask: number;
  change: number;
  changePct: number;
}

interface TickerState {
  XAUUSDB: TickerPrice;
  GBPJPYB: TickerPrice;
}

// Fetch GBP/JPY from Coinbase exchange rates (CORS-friendly, no auth).
// XAU/USD is seeded from mock (confirmed by user) — no reliable free intraday API.
async function fetchReferencePrices(): Promise<{ gj: number } | null> {
  try {
    const res = await fetch('https://api.coinbase.com/v2/exchange-rates?currency=GBP');
    if (!res.ok) return null;
    const data = await res.json();
    const gj: number = parseFloat(data?.data?.rates?.JPY);
    if (!gj || isNaN(gj)) return null;
    return { gj };
  } catch {
    return null;
  }
}

export function LiveTicker() {
  const [prices, setPrices] = useState<TickerState>({
    XAUUSDB: { ...LIVE_PRICES.XAUUSDB },
    GBPJPYB: { ...LIVE_PRICES.GBPJPYB },
  });

  const [flash, setFlash] = useState<{ XAUUSDB: 'up' | 'down' | null; GBPJPYB: 'up' | 'down' | null }>({
    XAUUSDB: null,
    GBPJPYB: null,
  });

  // Fetch GBP/JPY reference price from Coinbase on mount
  useEffect(() => {
    fetchReferencePrices().then(ref => {
      if (!ref) return;
      setPrices(prev => ({
        ...prev,
        GBPJPYB: {
          bid: parseFloat(ref.gj.toFixed(3)),
          ask: parseFloat((ref.gj + 0.020).toFixed(3)),
          change: prev.GBPJPYB.change,
          changePct: prev.GBPJPYB.changePct,
        },
      }));
    });
  }, []);

  // Intraday simulation: small random walk every 2 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setPrices(prev => {
        const xauDelta = (Math.random() - 0.5) * 0.80;
        const gjDelta = (Math.random() - 0.5) * 0.08;

        const newXauBid = parseFloat((prev.XAUUSDB.bid + xauDelta).toFixed(2));
        const newGjBid = parseFloat((prev.GBPJPYB.bid + gjDelta).toFixed(3));

        setFlash({
          XAUUSDB: xauDelta >= 0 ? 'up' : 'down',
          GBPJPYB: gjDelta >= 0 ? 'up' : 'down',
        });
        setTimeout(() => setFlash({ XAUUSDB: null, GBPJPYB: null }), 300);

        return {
          XAUUSDB: {
            bid: newXauBid,
            ask: parseFloat((newXauBid + 0.40).toFixed(2)),
            change: parseFloat((prev.XAUUSDB.change + xauDelta).toFixed(2)),
            changePct: parseFloat((prev.XAUUSDB.changePct + (xauDelta / prev.XAUUSDB.bid) * 100 * 0.05).toFixed(2)),
          },
          GBPJPYB: {
            bid: newGjBid,
            ask: parseFloat((newGjBid + 0.020).toFixed(3)),
            change: parseFloat((prev.GBPJPYB.change + gjDelta).toFixed(3)),
            changePct: parseFloat((prev.GBPJPYB.changePct + (gjDelta / prev.GBPJPYB.bid) * 100 * 0.05).toFixed(2)),
          },
        };
      });
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{
      background: 'rgba(10,10,26,0.95)',
      borderBottom: '1px solid rgba(212,168,67,0.10)',
      padding: '8px 16px',
      display: 'flex',
      alignItems: 'center',
      gap: 20,
      fontSize: 12,
      letterSpacing: 0.3,
    }}>
      {/* Live dot */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexShrink: 0 }}>
        <div style={{
          width: 6, height: 6, borderRadius: '50%',
          background: colors.buyGreen,
          boxShadow: `0 0 6px ${colors.buyGreen}`,
          animation: 'pulse 2s infinite',
        }} />
        <span style={{ fontSize: 10, color: colors.textMuted, fontWeight: 600 }}>LIVE</span>
      </div>

      <TickerItem pair="XAUUSDB" price={prices.XAUUSDB} decimals={2} flash={flash.XAUUSDB} prefix="$" />
      <div style={{ width: 1, height: 16, background: 'rgba(255,255,255,0.10)' }} />
      <TickerItem pair="GBPJPYB" price={prices.GBPJPYB} decimals={3} flash={flash.GBPJPYB} prefix="" />

      <div style={{ marginLeft: 'auto', fontSize: 10, color: colors.textMuted }}>
        SGT {new Date().toLocaleTimeString('en-SG', {
          hour: '2-digit', minute: '2-digit', second: '2-digit',
          timeZone: 'Asia/Singapore',
        })}
      </div>
    </div>
  );
}

function TickerItem({
  pair, price, decimals, flash, prefix,
}: {
  pair: string;
  price: TickerPrice;
  decimals: number;
  flash: 'up' | 'down' | null;
  prefix: string;
}) {
  const isUp = price.change >= 0;
  const arrowColor = isUp ? colors.buyGreen : colors.sellRed;
  const flashBg = flash === 'up' ? 'rgba(34,197,94,0.12)' : flash === 'down' ? 'rgba(239,68,68,0.12)' : 'transparent';

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '2px 6px', borderRadius: 6,
      background: flashBg, transition: 'background 0.15s ease',
    }}>
      <span style={{ color: colors.textMuted, fontWeight: 600, fontSize: 11 }}>{pair}</span>
      <span style={{
        color: colors.textPrimary, fontWeight: 700, fontSize: 13,
        fontFamily: "'SF Mono','Fira Code',monospace",
        transition: 'color 0.15s ease',
      }}>
        {prefix}{price.bid.toFixed(decimals)}
      </span>
      <span style={{ color: arrowColor, fontSize: 10, fontWeight: 700 }}>
        {isUp ? '▲' : '▼'} {isUp ? '+' : ''}{price.change.toFixed(decimals)} ({isUp ? '+' : ''}{price.changePct.toFixed(2)}%)
      </span>
    </div>
  );
}
