import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import type { UserProfile, UIMode, TradingStyle, Signal } from '../types';
import * as storage from '../services/storage';

// ── Auth Slice ────────────────────────────────────────────────────────────────

interface AuthSlice {
  user: UserProfile | null;
  token: string | null;
  isAuthenticated: boolean;
  setAuth: (user: UserProfile, token: string) => void;
  setUser: (user: UserProfile) => void;
  logout: () => void;
}

// ── UI Slice ──────────────────────────────────────────────────────────────────

interface UISlice {
  uiMode: UIMode;
  tradingStyle: TradingStyle;
  isSimpleMode: boolean;
  isProMode: boolean;
  isMaxMode: boolean;
  setUIMode: (mode: UIMode) => void;
  setTradingStyle: (style: TradingStyle) => void;
}

// ── Signals Slice ─────────────────────────────────────────────────────────────

interface SignalsSlice {
  activeSignals: Signal[];
  dismissedIds: Set<string>;
  setActiveSignals: (signals: Signal[]) => void;
  addOrUpdateSignal: (signal: Signal) => void;
  dismissSignal: (id: string) => void;
  removeSignal: (id: string) => void;
}

// ── Notifications Slice ───────────────────────────────────────────────────────

interface NotificationSlice {
  unreadCount: number;
  incrementUnread: () => void;
  markAllRead: () => void;
}

// ── Combined Store ────────────────────────────────────────────────────────────

type Store = AuthSlice & UISlice & SignalsSlice & NotificationSlice;

export const useStore = create<Store>()(
  subscribeWithSelector((set, get) => ({
    // Auth
    user: storage.getUser(),
    token: storage.getToken(),
    isAuthenticated: !!storage.getToken() && !!storage.getUser(),

    setAuth: (user, token) => {
      storage.setUser(user);
      storage.setToken(token);
      set({ user, token, isAuthenticated: true });
    },

    setUser: (user) => {
      storage.setUser(user);
      set({ user });
    },

    logout: () => {
      storage.clearAll();
      set({
        user: null,
        token: null,
        isAuthenticated: false,
        activeSignals: [],
        dismissedIds: new Set(),
        unreadCount: 0,
      });
    },

    // UI
    uiMode: storage.getUIMode(),
    tradingStyle: storage.getTradingStyle(),
    isSimpleMode: storage.getUIMode() === 'simple',
    isProMode: storage.getUIMode() === 'pro',
    isMaxMode: storage.getUIMode() === 'max',

    setUIMode: (mode) => {
      storage.setUIMode(mode);
      set({
        uiMode: mode,
        isSimpleMode: mode === 'simple',
        isProMode: mode === 'pro',
        isMaxMode: mode === 'max',
      });
    },

    setTradingStyle: (style) => {
      storage.setTradingStyle(style);
      set({ tradingStyle: style });
    },

    // Signals
    activeSignals: [],
    dismissedIds: new Set<string>(),

    setActiveSignals: (signals) => {
      const dismissed = get().dismissedIds;
      set({ activeSignals: signals.filter((s) => !dismissed.has(s.id)) });
    },

    addOrUpdateSignal: (signal) => {
      const dismissed = get().dismissedIds;
      if (dismissed.has(signal.id)) return;
      set((state) => {
        const existing = state.activeSignals.findIndex((s) => s.id === signal.id);
        if (existing >= 0) {
          const updated = [...state.activeSignals];
          updated[existing] = signal;
          return { activeSignals: updated };
        }
        return { activeSignals: [signal, ...state.activeSignals] };
      });
    },

    dismissSignal: (id) => {
      set((state) => {
        const newDismissed = new Set(state.dismissedIds);
        newDismissed.add(id);
        return {
          dismissedIds: newDismissed,
          activeSignals: state.activeSignals.filter((s) => s.id !== id),
        };
      });
    },

    removeSignal: (id) => {
      set((state) => ({
        activeSignals: state.activeSignals.filter((s) => s.id !== id),
      }));
    },

    // Notifications
    unreadCount: 0,

    incrementUnread: () => {
      set((state) => ({ unreadCount: state.unreadCount + 1 }));
    },

    markAllRead: () => {
      set({ unreadCount: 0 });
    },
  })),
);

// Convenience selectors
export const useAuth = () =>
  useStore((s) => ({
    user: s.user,
    token: s.token,
    isAuthenticated: s.isAuthenticated,
    setAuth: s.setAuth,
    setUser: s.setUser,
    logout: s.logout,
  }));

export const useUIMode = () =>
  useStore((s) => ({
    uiMode: s.uiMode,
    tradingStyle: s.tradingStyle,
    isSimpleMode: s.isSimpleMode,
    isProMode: s.isProMode,
    isMaxMode: s.isMaxMode,
    setUIMode: s.setUIMode,
    setTradingStyle: s.setTradingStyle,
  }));

export const useSignals = () =>
  useStore((s) => ({
    activeSignals: s.activeSignals,
    dismissedIds: s.dismissedIds,
    setActiveSignals: s.setActiveSignals,
    addOrUpdateSignal: s.addOrUpdateSignal,
    dismissSignal: s.dismissSignal,
    removeSignal: s.removeSignal,
  }));

export const useNotifications = () =>
  useStore((s) => ({
    unreadCount: s.unreadCount,
    incrementUnread: s.incrementUnread,
    markAllRead: s.markAllRead,
  }));
