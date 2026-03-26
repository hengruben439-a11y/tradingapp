import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Switch,
  StatusBar,
  Alert,
} from 'react-native';
import LinearGradient from 'react-native-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';

import { colors, spacing, typography, fontWeights, borderRadius } from '../../theme';
import { auth } from '../../services/api';
import * as storage from '../../services/storage';
import { useAuth, useUIMode } from '../../store';
import GlassCard from '../../components/GlassCard';
import type { UIMode, TradingStyle } from '../../types';

const TIMEZONES = [
  { label: 'SGT (UTC+8)', value: 'Asia/Singapore' },
  { label: 'EST (UTC-5)', value: 'America/New_York' },
  { label: 'GMT (UTC+0)', value: 'Europe/London' },
  { label: 'Auto-detect', value: 'auto' },
];

const TRADING_STYLE_OPTIONS: { label: string; value: TradingStyle; description: string }[] = [
  { label: 'Scalping', value: 'scalping', description: '1m-5m • 1-30 min hold • 1:1.5 R:R' },
  { label: 'Day Trading', value: 'day_trading', description: '15m-30m • 1-8h hold • 1:2 R:R' },
  { label: 'Swing Trading', value: 'swing_trading', description: '1H-4H • 1-14d hold • 1:3 R:R' },
  { label: 'Position', value: 'position_trading', description: '1D • 2-12w hold • 1:4 R:R' },
];

const UI_MODES: { label: string; value: UIMode; description: string; tier: 'free' | 'premium' | 'pro' }[] = [
  { label: 'Simple', value: 'simple', description: 'Top signals, plain labels, beginner-friendly', tier: 'free' },
  { label: 'Pro', value: 'pro', description: 'Full signals, module dissent, regime badges', tier: 'premium' },
  { label: 'Max', value: 'max', description: 'Raw scores, decay timer, advanced analytics', tier: 'pro' },
];

function SectionHeader({ title }: { title: string }) {
  return <Text style={styles.sectionHeader}>{title}</Text>;
}

function SettingsRow({
  label,
  value,
  onPress,
  right,
  description,
}: {
  label: string;
  value?: string;
  onPress?: () => void;
  right?: React.ReactNode;
  description?: string;
}) {
  return (
    <TouchableOpacity
      style={styles.settingsRow}
      onPress={onPress}
      disabled={!onPress && !right}
      activeOpacity={onPress ? 0.7 : 1}
    >
      <View style={styles.settingsRowLeft}>
        <Text style={styles.settingsRowLabel}>{label}</Text>
        {description && <Text style={styles.settingsRowDesc}>{description}</Text>}
      </View>
      {right ?? (value && <Text style={styles.settingsRowValue}>{value}</Text>)}
      {onPress && !right && <Text style={styles.chevron}>›</Text>}
    </TouchableOpacity>
  );
}

export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation();
  const { user, logout } = useAuth();
  const { uiMode, tradingStyle, setUIMode, setTradingStyle } = useUIMode();

  const [timezone, setTimezoneState] = useState(storage.getTimezone());
  const [paperTrading, setPaperTrading] = useState(storage.isPaperTradingEnabled());
  const [notifSignals, setNotifSignals] = useState(true);
  const [notifNews, setNotifNews] = useState(true);
  const [notifTpSl, setNotifTpSl] = useState(true);
  const [notifDaily, setNotifDaily] = useState(true);

  const tier = user?.subscriptionTier ?? 'free';

  const handleLogout = () => {
    Alert.alert('Sign Out', 'Are you sure you want to sign out?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign Out',
        style: 'destructive',
        onPress: async () => {
          await auth.logout();
          logout();
        },
      },
    ]);
  };

  const handleUIMode = (mode: UIMode) => {
    const modeReqs: Record<UIMode, typeof tier> = {
      simple: 'free',
      pro: 'premium',
      max: 'pro',
    };
    const required = modeReqs[mode];
    const tierOrder = ['free', 'premium', 'pro'];
    if (tierOrder.indexOf(tier) < tierOrder.indexOf(required)) {
      Alert.alert(
        'Upgrade Required',
        `${mode.charAt(0).toUpperCase() + mode.slice(1)} mode requires a ${required} subscription.`,
      );
      return;
    }
    setUIMode(mode);
  };

  const handlePaperTrading = (val: boolean) => {
    setPaperTrading(val);
    storage.setPaperTradingEnabled(val);
  };

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" />
      <LinearGradient
        colors={[colors.backgroundDeep, colors.ambientGradientEnd, colors.backgroundDeep]}
        style={StyleSheet.absoluteFill}
      />

      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 80 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.title}>Settings</Text>

        {/* Profile */}
        <GlassCard style={styles.card} padding={0}>
          <View style={styles.profileRow}>
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>
                {user?.displayName?.[0] ?? user?.email?.[0] ?? '?'}
              </Text>
            </View>
            <View style={styles.profileInfo}>
              <Text style={styles.profileName}>{user?.displayName ?? 'Trader'}</Text>
              <Text style={styles.profileEmail}>{user?.email ?? ''}</Text>
            </View>
            <View style={[styles.tierBadge, { backgroundColor: tier === 'pro' ? 'rgba(212,168,67,0.2)' : tier === 'premium' ? 'rgba(59,130,246,0.15)' : 'rgba(107,114,128,0.15)' }]}>
              <Text style={[styles.tierBadgeText, { color: tier === 'pro' ? colors.goldPrimary : tier === 'premium' ? colors.info : colors.textMuted }]}>
                {tier.toUpperCase()}
              </Text>
            </View>
          </View>
        </GlassCard>

        {/* Trading Style */}
        <SectionHeader title="Trading Style" />
        <GlassCard style={styles.card} padding={spacing.md}>
          {TRADING_STYLE_OPTIONS.map((opt, i) => (
            <TouchableOpacity
              key={opt.value}
              style={[
                styles.optionRow,
                i < TRADING_STYLE_OPTIONS.length - 1 && styles.optionRowBorder,
                tradingStyle === opt.value && styles.optionRowActive,
              ]}
              onPress={() => setTradingStyle(opt.value)}
            >
              <View style={styles.optionLeft}>
                <Text style={[styles.optionLabel, tradingStyle === opt.value && { color: colors.goldPrimary }]}>
                  {opt.label}
                </Text>
                <Text style={styles.optionDesc}>{opt.description}</Text>
              </View>
              {tradingStyle === opt.value && (
                <View style={styles.checkmark}>
                  <Text style={styles.checkmarkText}>✓</Text>
                </View>
              )}
            </TouchableOpacity>
          ))}
        </GlassCard>

        {/* UI Mode */}
        <SectionHeader title="Display Mode" />
        <GlassCard style={styles.card} padding={spacing.md}>
          {UI_MODES.map((opt, i) => {
            const tierOrder = ['free', 'premium', 'pro'];
            const locked = tierOrder.indexOf(tier) < tierOrder.indexOf(opt.tier);
            return (
              <TouchableOpacity
                key={opt.value}
                style={[
                  styles.optionRow,
                  i < UI_MODES.length - 1 && styles.optionRowBorder,
                  uiMode === opt.value && styles.optionRowActive,
                  locked && styles.optionRowLocked,
                ]}
                onPress={() => handleUIMode(opt.value)}
              >
                <View style={styles.optionLeft}>
                  <View style={styles.optionLabelRow}>
                    <Text style={[styles.optionLabel, uiMode === opt.value && { color: colors.goldPrimary }, locked && { color: colors.textMuted }]}>
                      {opt.label}
                    </Text>
                    {locked && (
                      <View style={styles.lockBadge}>
                        <Text style={styles.lockBadgeText}>{opt.tier.toUpperCase()}</Text>
                      </View>
                    )}
                  </View>
                  <Text style={[styles.optionDesc, locked && { color: colors.textMuted }]}>
                    {opt.description}
                  </Text>
                </View>
                {uiMode === opt.value && (
                  <View style={styles.checkmark}>
                    <Text style={styles.checkmarkText}>✓</Text>
                  </View>
                )}
              </TouchableOpacity>
            );
          })}
        </GlassCard>

        {/* Notifications */}
        <SectionHeader title="Notifications" />
        <GlassCard style={styles.card} padding={0}>
          <ToggleRow label="New Signals" value={notifSignals} onToggle={setNotifSignals} />
          <ToggleRow label="TP / SL Hits" value={notifTpSl} onToggle={setNotifTpSl} description="Alert when position hits target or stop" />
          <ToggleRow label="News Alerts" value={notifNews} onToggle={setNotifNews} description="15-min countdown before high-impact events" />
          <ToggleRow label="Daily Rundown" value={notifDaily} onToggle={setNotifDaily} description="6:00 AM SGT daily market summary" last />
        </GlassCard>

        {/* Preferences */}
        <SectionHeader title="Preferences" />
        <GlassCard style={styles.card} padding={0}>
          <SettingsRow
            label="Timezone"
            value={TIMEZONES.find((t) => t.value === timezone)?.label ?? timezone}
            onPress={() =>
              Alert.alert(
                'Select Timezone',
                '',
                TIMEZONES.map((tz) => ({
                  text: tz.label,
                  onPress: () => {
                    storage.setTimezone(tz.value);
                    setTimezoneState(tz.value);
                  },
                })),
              )
            }
          />
          <ToggleRow
            label="Paper Trading"
            value={paperTrading}
            onToggle={handlePaperTrading}
            description="Practice with virtual capital"
            last
          />
        </GlassCard>

        {/* Risk Defaults */}
        <SectionHeader title="Risk" />
        <GlassCard style={styles.card} padding={0}>
          <SettingsRow
            label="Risk Calculator"
            onPress={() => (navigation as any).navigate('RiskCalculator')}
          />
          <SettingsRow
            label="Default Balance"
            value={`$${storage.getAccountBalance().toLocaleString()}`}
            onPress={() => (navigation as any).navigate('RiskCalculator')}
          />
          <SettingsRow
            label="Default Risk %"
            value={`${storage.getRiskPct()}%`}
          />
        </GlassCard>

        {/* Broker */}
        <SectionHeader title="Broker Integration" />
        <GlassCard style={styles.card} padding={spacing.md}>
          <View style={styles.brokerPlaceholder}>
            <Text style={styles.brokerIcon}>🏦</Text>
            <Text style={styles.brokerTitle}>HFM MT4/MT5 Connection</Text>
            <Text style={styles.brokerDesc}>
              Broker integration via MetaApi available in Phase 3. Connect your HFM account to execute trades directly from signals.
            </Text>
          </View>
        </GlassCard>

        {/* Account */}
        <SectionHeader title="Account" />
        <GlassCard style={styles.card} padding={0}>
          <SettingsRow
            label="Subscription"
            value={tier.charAt(0).toUpperCase() + tier.slice(1)}
            onPress={() => Alert.alert('Subscription', 'Manage subscription through App Store.')}
          />
          <SettingsRow
            label="Privacy Policy"
            onPress={() => {}}
          />
          <SettingsRow
            label="Terms of Service"
            onPress={() => {}}
          />
        </GlassCard>

        {/* Disclaimer */}
        <View style={styles.disclaimer}>
          <Text style={styles.disclaimerText}>
            Trading foreign exchange and CFDs carries a high level of risk. made. provides algorithmic analysis and educational information only — not financial advice. Past performance is not indicative of future results.
          </Text>
        </View>

        {/* Logout */}
        <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
          <Text style={styles.logoutText}>Sign Out</Text>
        </TouchableOpacity>

        <Text style={styles.version}>made. v1.0.0 · Phase 1</Text>
      </ScrollView>
    </View>
  );
}

function ToggleRow({
  label,
  value,
  onToggle,
  description,
  last = false,
}: {
  label: string;
  value: boolean;
  onToggle: (val: boolean) => void;
  description?: string;
  last?: boolean;
}) {
  return (
    <View style={[styles.settingsRow, !last && styles.settingsRowBorder]}>
      <View style={styles.settingsRowLeft}>
        <Text style={styles.settingsRowLabel}>{label}</Text>
        {description && <Text style={styles.settingsRowDesc}>{description}</Text>}
      </View>
      <Switch
        value={value}
        onValueChange={onToggle}
        trackColor={{ false: colors.glassBorder, true: colors.goldBorderStrong }}
        thumbColor={value ? colors.goldPrimary : colors.textMuted}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.backgroundDeep },
  content: { paddingHorizontal: spacing.lg, gap: spacing.sm },
  title: { ...typography.headingLarge, color: colors.textPrimary, marginBottom: spacing.xs },
  sectionHeader: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: fontWeights.semibold,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginTop: spacing.md,
    marginLeft: spacing.sm,
  },
  card: { marginBottom: 0 },
  profileRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.lg,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: 'rgba(212,168,67,0.2)',
    borderWidth: 1.5,
    borderColor: colors.goldBorderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: colors.goldPrimary, fontSize: 20, fontWeight: fontWeights.bold },
  profileInfo: { flex: 1 },
  profileName: { color: colors.textPrimary, fontSize: 16, fontWeight: fontWeights.semibold },
  profileEmail: { color: colors.textSecondary, fontSize: 13, marginTop: 2 },
  tierBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: borderRadius.sm,
  },
  tierBadgeText: { fontSize: 10, fontWeight: fontWeights.bold, letterSpacing: 0.5 },
  optionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
  },
  optionRowBorder: { borderBottomWidth: 1, borderBottomColor: colors.glassBorder },
  optionRowActive: { backgroundColor: 'rgba(212,168,67,0.06)' },
  optionRowLocked: { opacity: 0.5 },
  optionLeft: { flex: 1 },
  optionLabelRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  optionLabel: { color: colors.textPrimary, fontSize: 15, fontWeight: fontWeights.medium },
  optionDesc: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  checkmark: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: 'rgba(212,168,67,0.2)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkmarkText: { color: colors.goldPrimary, fontSize: 13, fontWeight: fontWeights.bold },
  lockBadge: {
    backgroundColor: 'rgba(107,114,128,0.15)',
    borderRadius: 3,
    paddingHorizontal: 4,
    paddingVertical: 1,
  },
  lockBadgeText: { color: colors.textMuted, fontSize: 9, fontWeight: fontWeights.bold },
  settingsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.glassBorder,
  },
  settingsRowBorder: { borderBottomWidth: 1, borderBottomColor: colors.glassBorder },
  settingsRowLeft: { flex: 1 },
  settingsRowLabel: { color: colors.textPrimary, fontSize: 15 },
  settingsRowDesc: { color: colors.textMuted, fontSize: 12, marginTop: 1 },
  settingsRowValue: { color: colors.textSecondary, fontSize: 14 },
  chevron: { color: colors.textMuted, fontSize: 20, marginLeft: spacing.sm },
  brokerPlaceholder: { alignItems: 'center', padding: spacing.lg, gap: spacing.md },
  brokerIcon: { fontSize: 36 },
  brokerTitle: { color: colors.textPrimary, fontSize: 16, fontWeight: fontWeights.semibold, textAlign: 'center' },
  brokerDesc: { color: colors.textSecondary, fontSize: 13, textAlign: 'center', lineHeight: 20 },
  disclaimer: {
    backgroundColor: 'rgba(255,255,255,0.03)',
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    padding: spacing.md,
    marginTop: spacing.sm,
  },
  disclaimerText: { color: colors.textMuted, fontSize: 11, lineHeight: 18, textAlign: 'center' },
  logoutBtn: {
    paddingVertical: spacing.lg,
    borderRadius: borderRadius.xl,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(239,68,68,0.3)',
    marginTop: spacing.sm,
  },
  logoutText: { color: colors.sellRed, fontSize: 16, fontWeight: fontWeights.semibold },
  version: { color: colors.textMuted, fontSize: 11, textAlign: 'center', marginTop: spacing.sm },
});
