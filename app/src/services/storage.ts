import { MMKV } from 'react-native-mmkv';
import type { UserProfile, UIMode, TradingStyle } from '../types';

const storage = new MMKV({
  id: 'made-storage',
  encryptionKey: 'made-secure-key',
});

const KEYS = {
  TOKEN: 'auth_token',
  REFRESH_TOKEN: 'refresh_token',
  USER: 'user_profile',
  UI_MODE: 'ui_mode',
  TRADING_STYLE: 'trading_style',
  ONBOARDING_COMPLETED: 'onboarding_completed',
  ACCOUNT_BALANCE: 'account_balance',
  RISK_PCT: 'risk_pct',
  TIMEZONE: 'timezone',
  PAPER_TRADING: 'paper_trading',
} as const;

// Auth token
export function getToken(): string | null {
  return storage.getString(KEYS.TOKEN) ?? null;
}

export function setToken(token: string): void {
  storage.set(KEYS.TOKEN, token);
}

export function clearToken(): void {
  storage.delete(KEYS.TOKEN);
}

export function getRefreshToken(): string | null {
  return storage.getString(KEYS.REFRESH_TOKEN) ?? null;
}

export function setRefreshToken(token: string): void {
  storage.set(KEYS.REFRESH_TOKEN, token);
}

// User profile
export function getUser(): UserProfile | null {
  const raw = storage.getString(KEYS.USER);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserProfile;
  } catch {
    return null;
  }
}

export function setUser(user: UserProfile): void {
  storage.set(KEYS.USER, JSON.stringify(user));
}

export function clearUser(): void {
  storage.delete(KEYS.USER);
}

// UI Mode
export function getUIMode(): UIMode {
  return (storage.getString(KEYS.UI_MODE) as UIMode) ?? 'simple';
}

export function setUIMode(mode: UIMode): void {
  storage.set(KEYS.UI_MODE, mode);
}

// Trading style
export function getTradingStyle(): TradingStyle {
  return (storage.getString(KEYS.TRADING_STYLE) as TradingStyle) ?? 'day_trading';
}

export function setTradingStyle(style: TradingStyle): void {
  storage.set(KEYS.TRADING_STYLE, style);
}

// Onboarding
export function isOnboardingCompleted(): boolean {
  return storage.getBoolean(KEYS.ONBOARDING_COMPLETED) ?? false;
}

export function setOnboardingCompleted(value: boolean): void {
  storage.set(KEYS.ONBOARDING_COMPLETED, value);
}

// Trading preferences
export function getAccountBalance(): number {
  return storage.getNumber(KEYS.ACCOUNT_BALANCE) ?? 10000;
}

export function setAccountBalance(balance: number): void {
  storage.set(KEYS.ACCOUNT_BALANCE, balance);
}

export function getRiskPct(): number {
  return storage.getNumber(KEYS.RISK_PCT) ?? 1.0;
}

export function setRiskPct(pct: number): void {
  storage.set(KEYS.RISK_PCT, pct);
}

export function getTimezone(): string {
  return storage.getString(KEYS.TIMEZONE) ?? 'Asia/Singapore';
}

export function setTimezone(tz: string): void {
  storage.set(KEYS.TIMEZONE, tz);
}

export function isPaperTradingEnabled(): boolean {
  return storage.getBoolean(KEYS.PAPER_TRADING) ?? true;
}

export function setPaperTradingEnabled(value: boolean): void {
  storage.set(KEYS.PAPER_TRADING, value);
}

// Clear all (logout)
export function clearAll(): void {
  storage.clearAll();
}
