import { getToken, setToken, setRefreshToken, clearAll } from './storage';
import type {
  Signal,
  JournalEntry,
  CalendarEvent,
  UserProfile,
  AnalyticsSummary,
  EquityCurvePoint,
  MonthlyPnl,
  TradingStyle,
  UIMode,
} from '../types';

const API_BASE_URL = process.env.API_BASE_URL ?? 'http://localhost:8000';

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}

interface AuthResponse {
  accessToken: string;
  refreshToken: string;
  user: UserProfile;
}

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    // Attempt token refresh
    const refreshed = await attemptRefresh();
    if (refreshed) {
      return request<T>(path, options);
    }
    clearAll();
    throw new ApiError(401, 'Session expired');
  }

  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || `HTTP ${res.status}`);
  }

  return res.json() as Promise<T>;
}

async function attemptRefresh(): Promise<boolean> {
  try {
    const { getRefreshToken } = await import('./storage');
    const refresh = getRefreshToken();
    if (!refresh) return false;

    const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refreshToken: refresh }),
    });

    if (!res.ok) return false;

    const data = (await res.json()) as { accessToken: string; refreshToken: string };
    setToken(data.accessToken);
    setRefreshToken(data.refreshToken);
    return true;
  } catch {
    return false;
  }
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export const auth = {
  async login(email: string, password: string): Promise<AuthResponse> {
    return request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  async refresh(): Promise<{ accessToken: string; refreshToken: string }> {
    const { getRefreshToken } = await import('./storage');
    return request('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refreshToken: getRefreshToken() }),
    });
  },

  async logout(): Promise<void> {
    try {
      await request('/auth/logout', { method: 'POST' });
    } finally {
      clearAll();
    }
  },

  async getMe(): Promise<UserProfile> {
    return request<UserProfile>('/auth/me');
  },

  async updateMe(data: Partial<UserProfile>): Promise<UserProfile> {
    return request<UserProfile>('/auth/me', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },
};

// ── Signals ───────────────────────────────────────────────────────────────────

export const signals = {
  async getActiveSignals(style?: TradingStyle): Promise<Signal[]> {
    const qs = style ? `?style=${style}` : '';
    return request<Signal[]>(`/signals/active${qs}`);
  },

  async getSignalHistory(page = 1, pageSize = 20): Promise<PaginatedResponse<Signal>> {
    return request<PaginatedResponse<Signal>>(
      `/signals/history?page=${page}&pageSize=${pageSize}`,
    );
  },

  async getSignal(id: string): Promise<Signal> {
    return request<Signal>(`/signals/${id}`);
  },
};

// ── Journal ───────────────────────────────────────────────────────────────────

export const journal = {
  async getJournal(
    page = 1,
    filter?: 'open' | 'closed' | 'paper',
  ): Promise<PaginatedResponse<JournalEntry>> {
    const qs = new URLSearchParams({ page: String(page) });
    if (filter) qs.set('filter', filter);
    return request<PaginatedResponse<JournalEntry>>(`/journal?${qs}`);
  },

  async createEntry(entry: Partial<JournalEntry>): Promise<JournalEntry> {
    return request<JournalEntry>('/journal', {
      method: 'POST',
      body: JSON.stringify(entry),
    });
  },

  async updateEntry(id: string, data: Partial<JournalEntry>): Promise<JournalEntry> {
    return request<JournalEntry>(`/journal/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async getStats(): Promise<AnalyticsSummary> {
    return request<AnalyticsSummary>('/journal/stats');
  },
};

// ── Calendar ──────────────────────────────────────────────────────────────────

export const calendar = {
  async getToday(): Promise<CalendarEvent[]> {
    return request<CalendarEvent[]>('/calendar/today');
  },

  async getUpcoming(days = 7): Promise<CalendarEvent[]> {
    return request<CalendarEvent[]>(`/calendar/upcoming?days=${days}`);
  },

  async getNextEvent(): Promise<CalendarEvent | null> {
    return request<CalendarEvent | null>('/calendar/next');
  },
};

// ── Analytics ─────────────────────────────────────────────────────────────────

export const analytics = {
  async getSummary(): Promise<AnalyticsSummary> {
    return request<AnalyticsSummary>('/analytics/summary');
  },

  async getEquityCurve(days = 90): Promise<EquityCurvePoint[]> {
    return request<EquityCurvePoint[]>(`/analytics/equity-curve?days=${days}`);
  },

  async getMonthlyPnl(): Promise<MonthlyPnl[]> {
    return request<MonthlyPnl[]>('/analytics/monthly-pnl');
  },

  async getBySession(): Promise<Record<string, AnalyticsSummary>> {
    return request<Record<string, AnalyticsSummary>>('/analytics/by-session');
  },
};

// ── Risk ──────────────────────────────────────────────────────────────────────

export const risk = {
  async calculate(params: {
    pair: string;
    balance: number;
    riskPct: number;
    slPips: number;
  }) {
    return request<{ lotSize: number; dollarRisk: number; marginRequired: number; pipValue: number }>(
      '/risk/calculate',
      { method: 'POST', body: JSON.stringify(params) },
    );
  },
};

export { ApiError };
