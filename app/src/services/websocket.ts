import { useEffect, useRef, useState, useCallback } from 'react';
import { getToken } from './storage';
import type { Signal, NewsAlert, WebSocketEvent } from '../types';

const WS_BASE_URL = (process.env.API_BASE_URL ?? 'http://localhost:8000').replace(/^http/, 'ws');

type WSStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

interface UseWebSocketReturn {
  connected: boolean;
  status: WSStatus;
  lastSignal: Signal | null;
  lastAlert: NewsAlert | null;
  lastTPHit: { signalId: string; tpLevel: number; pnl: number } | null;
  lastSLHit: { signalId: string; pnl: number } | null;
}

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000];

let globalSocket: WebSocket | null = null;
let globalListeners: Set<(event: WebSocketEvent) => void> = new Set();
let reconnectAttempt = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let intentionalClose = false;

function getReconnectDelay(): number {
  return RECONNECT_DELAYS[Math.min(reconnectAttempt, RECONNECT_DELAYS.length - 1)];
}

function connect(): void {
  if (globalSocket?.readyState === WebSocket.OPEN) return;

  const token = getToken();
  if (!token) return;

  const url = `${WS_BASE_URL}/ws?token=${encodeURIComponent(token)}`;
  globalSocket = new WebSocket(url);

  globalSocket.onopen = () => {
    reconnectAttempt = 0;
    notifyListeners({ type: 'pong', payload: { status: 'connected' }, timestamp: new Date().toISOString() });
    // Start ping interval
    startPing();
  };

  globalSocket.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data as string) as WebSocketEvent;
      notifyListeners(parsed);
    } catch {
      // ignore malformed messages
    }
  };

  globalSocket.onclose = () => {
    if (!intentionalClose) {
      scheduleReconnect();
    }
  };

  globalSocket.onerror = () => {
    globalSocket?.close();
  };
}

let pingInterval: ReturnType<typeof setInterval> | null = null;

function startPing(): void {
  if (pingInterval) clearInterval(pingInterval);
  pingInterval = setInterval(() => {
    if (globalSocket?.readyState === WebSocket.OPEN) {
      globalSocket.send(JSON.stringify({ type: 'ping' }));
    }
  }, 30000);
}

function scheduleReconnect(): void {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  const delay = getReconnectDelay();
  reconnectAttempt++;
  reconnectTimer = setTimeout(() => {
    connect();
  }, delay);
}

function notifyListeners(event: WebSocketEvent): void {
  globalListeners.forEach((listener) => listener(event));
}

export function initWebSocket(): void {
  intentionalClose = false;
  connect();
}

export function closeWebSocket(): void {
  intentionalClose = true;
  if (pingInterval) clearInterval(pingInterval);
  if (reconnectTimer) clearTimeout(reconnectTimer);
  globalSocket?.close();
  globalSocket = null;
}

export function useWebSocket(): UseWebSocketReturn {
  const [status, setStatus] = useState<WSStatus>('disconnected');
  const [lastSignal, setLastSignal] = useState<Signal | null>(null);
  const [lastAlert, setLastAlert] = useState<NewsAlert | null>(null);
  const [lastTPHit, setLastTPHit] = useState<{ signalId: string; tpLevel: number; pnl: number } | null>(null);
  const [lastSLHit, setLastSLHit] = useState<{ signalId: string; pnl: number } | null>(null);

  const handleEvent = useCallback((event: WebSocketEvent) => {
    switch (event.type) {
      case 'pong':
        setStatus((event.payload as { status: string }).status === 'connected' ? 'connected' : 'disconnected');
        break;
      case 'signal':
        setLastSignal(event.payload as Signal);
        break;
      case 'news_alert':
        setLastAlert(event.payload as NewsAlert);
        break;
      case 'tp_hit':
        setLastTPHit(event.payload as { signalId: string; tpLevel: number; pnl: number });
        break;
      case 'sl_hit':
        setLastSLHit(event.payload as { signalId: string; pnl: number });
        break;
    }
  }, []);

  useEffect(() => {
    globalListeners.add(handleEvent);

    if (!globalSocket || globalSocket.readyState === WebSocket.CLOSED) {
      setStatus('connecting');
      connect();
    } else if (globalSocket.readyState === WebSocket.OPEN) {
      setStatus('connected');
    }

    return () => {
      globalListeners.delete(handleEvent);
    };
  }, [handleEvent]);

  return {
    connected: status === 'connected',
    status,
    lastSignal,
    lastAlert,
    lastTPHit,
    lastSLHit,
  };
}
