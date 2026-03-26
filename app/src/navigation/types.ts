import type { NavigatorScreenParams } from '@react-navigation/native';

export type AuthStackParamList = {
  Login: undefined;
  Onboarding: undefined;
};

export type HomeStackParamList = {
  Dashboard: undefined;
  SignalDetail: { signalId: string };
};

export type JournalStackParamList = {
  Journal: undefined;
  JournalDetail: { entryId: string };
};

export type AppTabsParamList = {
  HomeTab: NavigatorScreenParams<HomeStackParamList>;
  CalendarTab: undefined;
  JournalTab: NavigatorScreenParams<JournalStackParamList>;
  SettingsTab: undefined;
};

export type RootStackParamList = {
  Auth: NavigatorScreenParams<AuthStackParamList>;
  App: NavigatorScreenParams<AppTabsParamList>;
  RiskCalculator: { signalId?: string } | undefined;
  BrokerConnect: undefined;
  TradeConfirm: { signalId: string };
  Subscription: { highlightTier?: 'premium' | 'pro' } | undefined;
};

declare global {
  namespace ReactNavigation {
    interface RootParamList extends RootStackParamList {}
  }
}
