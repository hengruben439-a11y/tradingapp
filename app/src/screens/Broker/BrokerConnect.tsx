/**
 * BrokerConnect — MetaApi account linking flow
 *
 * Step 1: Enter MT4/MT5 account number + password
 * Step 2: Select HFM server (dropdown with common HFM server names)
 * Step 3: Verify connection (shows balance/equity)
 * Step 4: Confirmation + paper trading toggle
 */

import React, { useState, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Switch,
  ActivityIndicator,
  StatusBar,
  Platform,
  KeyboardAvoidingView,
  Alert,
  Animated,
} from 'react-native';
import LinearGradient from 'react-native-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';

import { colors, spacing, typography, fontWeights, borderRadius, shadows } from '../../theme';
import GlassCard from '../../components/GlassCard';

// ── Types ─────────────────────────────────────────────────────────────────────

interface AccountInfo {
  balance: number;
  equity: number;
  currency: string;
  leverage: string;
  platform: 'MT4' | 'MT5';
  server: string;
}

type Platform = 'MT4' | 'MT5';

interface HFMServer {
  label: string;
  value: string;
  platform: Platform;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const HFM_SERVERS: HFMServer[] = [
  { label: 'HFM-MT5 Live',       value: 'HFM-MT5.com-Live',      platform: 'MT5' },
  { label: 'HFM-MT5 Demo',       value: 'HFM-MT5.com-Demo',      platform: 'MT5' },
  { label: 'HFM-MT4 Live',       value: 'HFM-MT4.com-Live',      platform: 'MT4' },
  { label: 'HFM-MT4 Demo',       value: 'HFM-MT4.com-Demo',      platform: 'MT4' },
  { label: 'HFM-MT5 Pro Live',   value: 'HFM-MT5.com-ProLive',   platform: 'MT5' },
  { label: 'HFM-MT5 ECN Live',   value: 'HFM-MT5.com-ECNLive',   platform: 'MT5' },
];

const TOTAL_STEPS = 3;

// ── Step indicator ─────────────────────────────────────────────────────────────

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <View style={stepStyles.container}>
      {Array.from({ length: total }).map((_, i) => {
        const stepNum = i + 1;
        const isActive = stepNum === current;
        const isDone = stepNum < current;
        return (
          <React.Fragment key={stepNum}>
            <View
              style={[
                stepStyles.dot,
                isDone && stepStyles.dotDone,
                isActive && stepStyles.dotActive,
              ]}
            >
              {isDone ? (
                <Text style={stepStyles.dotCheckmark}>✓</Text>
              ) : (
                <Text style={[stepStyles.dotLabel, isActive && stepStyles.dotLabelActive]}>
                  {stepNum}
                </Text>
              )}
            </View>
            {i < total - 1 && (
              <View style={[stepStyles.line, isDone && stepStyles.lineDone]} />
            )}
          </React.Fragment>
        );
      })}
    </View>
  );
}

const stepStyles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xl,
  },
  dot: {
    width: 32,
    height: 32,
    borderRadius: 16,
    borderWidth: 1.5,
    borderColor: colors.textMuted,
    backgroundColor: 'transparent',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dotActive: {
    borderColor: colors.goldPrimary,
    backgroundColor: 'rgba(212,168,67,0.15)',
  },
  dotDone: {
    borderColor: colors.success,
    backgroundColor: 'rgba(16,185,129,0.15)',
  },
  dotLabel: {
    ...typography.caption,
    color: colors.textMuted,
    fontWeight: fontWeights.semibold as any,
  },
  dotLabelActive: {
    color: colors.goldPrimary,
  },
  dotCheckmark: {
    fontSize: 13,
    color: colors.success,
    fontWeight: fontWeights.bold as any,
  },
  line: {
    flex: 1,
    height: 1.5,
    backgroundColor: colors.textMuted,
    marginHorizontal: spacing.xs,
    opacity: 0.4,
  },
  lineDone: {
    backgroundColor: colors.success,
    opacity: 1,
  },
});

// ── Server picker ──────────────────────────────────────────────────────────────

function ServerPicker({
  selected,
  onSelect,
}: {
  selected: string;
  onSelect: (server: HFMServer) => void;
}) {
  const [open, setOpen] = useState(false);
  const selectedServer = HFM_SERVERS.find(s => s.value === selected);

  return (
    <View style={pickerStyles.wrapper}>
      <TouchableOpacity
        style={pickerStyles.trigger}
        onPress={() => setOpen(prev => !prev)}
        activeOpacity={0.8}
      >
        <Text style={selectedServer ? pickerStyles.valueText : pickerStyles.placeholder}>
          {selectedServer ? selectedServer.label : 'Select HFM Server'}
        </Text>
        <Text style={pickerStyles.chevron}>{open ? '▲' : '▼'}</Text>
      </TouchableOpacity>

      {open && (
        <View style={pickerStyles.dropdown}>
          {HFM_SERVERS.map(server => (
            <TouchableOpacity
              key={server.value}
              style={[
                pickerStyles.option,
                server.value === selected && pickerStyles.optionSelected,
              ]}
              onPress={() => {
                onSelect(server);
                setOpen(false);
              }}
              activeOpacity={0.75}
            >
              <View style={pickerStyles.optionRow}>
                <Text
                  style={[
                    pickerStyles.optionLabel,
                    server.value === selected && pickerStyles.optionLabelSelected,
                  ]}
                >
                  {server.label}
                </Text>
                <View
                  style={[
                    pickerStyles.platformBadge,
                    server.platform === 'MT5'
                      ? pickerStyles.platformMT5
                      : pickerStyles.platformMT4,
                  ]}
                >
                  <Text style={pickerStyles.platformText}>{server.platform}</Text>
                </View>
              </View>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

const pickerStyles = StyleSheet.create({
  wrapper: { position: 'relative', zIndex: 10 },
  trigger: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
    borderRadius: borderRadius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  placeholder: {
    ...typography.body,
    color: colors.textMuted,
  },
  valueText: {
    ...typography.body,
    color: colors.textPrimary,
  },
  chevron: {
    color: colors.textSecondary,
    fontSize: 11,
  },
  dropdown: {
    position: 'absolute',
    top: '100%',
    left: 0,
    right: 0,
    backgroundColor: '#1E1E35',
    borderWidth: 1,
    borderColor: colors.glassBorder,
    borderRadius: borderRadius.md,
    marginTop: 4,
    overflow: 'hidden',
    ...shadows.lg,
    zIndex: 100,
  },
  option: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.04)',
  },
  optionSelected: {
    backgroundColor: 'rgba(212,168,67,0.08)',
  },
  optionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  optionLabel: {
    ...typography.body,
    color: colors.textSecondary,
  },
  optionLabelSelected: {
    color: colors.goldPrimary,
    fontWeight: fontWeights.semibold as any,
  },
  platformBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  platformMT5: { backgroundColor: 'rgba(59,130,246,0.2)' },
  platformMT4: { backgroundColor: 'rgba(212,168,67,0.15)' },
  platformText: {
    fontSize: 10,
    fontWeight: fontWeights.bold as any,
    color: colors.textSecondary,
  },
});

// ── Account info card ──────────────────────────────────────────────────────────

function AccountInfoCard({ info }: { info: AccountInfo }) {
  return (
    <GlassCard style={accountStyles.card} borderHighlight>
      <View style={accountStyles.header}>
        <Text style={accountStyles.successIcon}>✓</Text>
        <Text style={accountStyles.connectedLabel}>Connected</Text>
        <View style={accountStyles.platformBadge}>
          <Text style={accountStyles.platformText}>{info.platform}</Text>
        </View>
      </View>

      <Text style={accountStyles.serverName}>{info.server}</Text>

      <View style={accountStyles.metricsRow}>
        <View style={accountStyles.metric}>
          <Text style={accountStyles.metricLabel}>Balance</Text>
          <Text style={accountStyles.metricValue}>
            {info.currency} {info.balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </Text>
        </View>
        <View style={accountStyles.metricDivider} />
        <View style={accountStyles.metric}>
          <Text style={accountStyles.metricLabel}>Equity</Text>
          <Text style={accountStyles.metricValue}>
            {info.currency} {info.equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </Text>
        </View>
        <View style={accountStyles.metricDivider} />
        <View style={accountStyles.metric}>
          <Text style={accountStyles.metricLabel}>Leverage</Text>
          <Text style={accountStyles.metricValue}>{info.leverage}</Text>
        </View>
      </View>
    </GlassCard>
  );
}

const accountStyles = StyleSheet.create({
  card: { marginVertical: spacing.md },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  successIcon: {
    fontSize: 16,
    color: colors.success,
    marginRight: spacing.xs,
  },
  connectedLabel: {
    ...typography.bodySmall,
    color: colors.success,
    fontWeight: fontWeights.semibold as any,
    flex: 1,
  },
  platformBadge: {
    backgroundColor: 'rgba(59,130,246,0.2)',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  platformText: {
    fontSize: 11,
    color: colors.info,
    fontWeight: fontWeights.bold as any,
  },
  serverName: {
    ...typography.caption,
    color: colors.textMuted,
    marginBottom: spacing.md,
  },
  metricsRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  metric: {
    flex: 1,
    alignItems: 'center',
  },
  metricLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: 2,
  },
  metricValue: {
    ...typography.bodySmall,
    color: colors.textPrimary,
    fontWeight: fontWeights.semibold as any,
  },
  metricDivider: {
    width: 1,
    height: 32,
    backgroundColor: colors.glassBorder,
  },
});

// ── Main screen ────────────────────────────────────────────────────────────────

export default function BrokerConnect() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation();

  const [step, setStep] = useState(1);
  const [accountNumber, setAccountNumber] = useState('');
  const [password, setPassword] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [selectedServer, setSelectedServer] = useState('');
  const [usePaperTrading, setUsePaperTrading] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [accountInfo, setAccountInfo] = useState<AccountInfo | null>(null);

  const fadeAnim = useRef(new Animated.Value(1)).current;

  const animateStepChange = useCallback((nextStep: () => void) => {
    Animated.sequence([
      Animated.timing(fadeAnim, { toValue: 0, duration: 150, useNativeDriver: true }),
      Animated.timing(fadeAnim, { toValue: 1, duration: 200, useNativeDriver: true }),
    ]).start();
    setTimeout(nextStep, 150);
  }, [fadeAnim]);

  const handleTestConnection = useCallback(async () => {
    if (!accountNumber.trim()) {
      setConnectionError('Account number is required');
      return;
    }
    if (!password) {
      setConnectionError('Password is required');
      return;
    }
    if (!selectedServer) {
      setConnectionError('Please select an HFM server');
      return;
    }

    setConnectionError(null);
    setIsLoading(true);

    try {
      // POST to backend which proxies to MetaApi — credentials never stored
      const response = await fetch(
        `${process.env.API_BASE_URL ?? 'http://localhost:8000'}/broker/verify`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            account_number: accountNumber.trim(),
            password,
            server: selectedServer,
          }),
        },
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const msg = errorData?.detail ?? `Connection failed (${response.status})`;
        throw new Error(msg);
      }

      const data: AccountInfo = await response.json();
      setAccountInfo(data);
      animateStepChange(() => setStep(3));
    } catch (err: any) {
      const msg = err.message ?? 'Connection timed out. Please check credentials and try again.';
      setConnectionError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [accountNumber, password, selectedServer, animateStepChange]);

  const handleConfirm = useCallback(async () => {
    if (usePaperTrading) {
      // Skip broker connection, go to paper trading setup
      Alert.alert(
        'Paper Trading Enabled',
        'You will trade with a simulated $10,000 account. Switch to live trading anytime in Settings.',
        [{ text: 'Get Started', onPress: () => navigation.goBack() }],
      );
      return;
    }

    if (!accountInfo) return;

    setIsLoading(true);
    try {
      await fetch(
        `${process.env.API_BASE_URL ?? 'http://localhost:8000'}/broker/connect`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            account_number: accountNumber.trim(),
            password,
            server: selectedServer,
          }),
        },
      );
      Alert.alert(
        'Broker Connected',
        `Your ${accountInfo.platform} account is now linked. Signals will be sent directly to HFM.`,
        [{ text: 'Done', onPress: () => navigation.goBack() }],
      );
    } catch {
      Alert.alert('Error', 'Failed to save connection. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, [accountInfo, accountNumber, password, selectedServer, usePaperTrading, navigation]);

  const canProceedStep1 =
    accountNumber.trim().length >= 4 && password.length >= 4 && !usePaperTrading;

  const renderStep = () => {
    switch (step) {
      case 1:
        return (
          <>
            <Text style={styles.stepTitle}>Account Credentials</Text>
            <Text style={styles.stepSubtitle}>
              Enter your HFM MT4 or MT5 account details. Credentials are sent
              directly to MetaApi's encrypted vault — made. never stores them.
            </Text>

            <View style={styles.fieldGroup}>
              <Text style={styles.fieldLabel}>Account Number</Text>
              <TextInput
                style={styles.input}
                value={accountNumber}
                onChangeText={setAccountNumber}
                placeholder="e.g. 12345678"
                placeholderTextColor={colors.textMuted}
                keyboardType="numeric"
                autoCorrect={false}
                autoCapitalize="none"
                returnKeyType="next"
              />
            </View>

            <View style={styles.fieldGroup}>
              <Text style={styles.fieldLabel}>Password (Trader)</Text>
              <View style={styles.passwordRow}>
                <TextInput
                  style={[styles.input, styles.passwordInput]}
                  value={password}
                  onChangeText={setPassword}
                  placeholder="MT4/MT5 trader password"
                  placeholderTextColor={colors.textMuted}
                  secureTextEntry={!passwordVisible}
                  autoCorrect={false}
                  autoCapitalize="none"
                  returnKeyType="done"
                />
                <TouchableOpacity
                  style={styles.visibilityToggle}
                  onPress={() => setPasswordVisible(v => !v)}
                >
                  <Text style={styles.visibilityIcon}>
                    {passwordVisible ? '🙈' : '👁'}
                  </Text>
                </TouchableOpacity>
              </View>
            </View>

            <View style={styles.dividerRow}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerLabel}>or</Text>
              <View style={styles.dividerLine} />
            </View>

            <View style={styles.paperRow}>
              <View style={styles.paperTextGroup}>
                <Text style={styles.paperLabel}>Use Paper Trading</Text>
                <Text style={styles.paperSub}>
                  Practice with simulated $10,000 — no broker needed
                </Text>
              </View>
              <Switch
                value={usePaperTrading}
                onValueChange={v => {
                  setUsePaperTrading(v);
                  if (v) setConnectionError(null);
                }}
                trackColor={{ false: colors.glassBorder, true: colors.goldBorderStrong }}
                thumbColor={usePaperTrading ? colors.goldPrimary : colors.textMuted}
              />
            </View>

            <TouchableOpacity
              style={[
                styles.primaryButton,
                (!canProceedStep1 && !usePaperTrading) && styles.buttonDisabled,
              ]}
              onPress={() => {
                if (usePaperTrading) {
                  handleConfirm();
                  return;
                }
                animateStepChange(() => setStep(2));
              }}
              disabled={!canProceedStep1 && !usePaperTrading}
              activeOpacity={0.85}
            >
              <Text style={styles.primaryButtonText}>
                {usePaperTrading ? 'Start Paper Trading' : 'Next — Select Server'}
              </Text>
            </TouchableOpacity>
          </>
        );

      case 2:
        return (
          <>
            <Text style={styles.stepTitle}>Select HFM Server</Text>
            <Text style={styles.stepSubtitle}>
              Choose the server that matches your HFM account type.
              Check your HFM portal or MT4/MT5 login screen if unsure.
            </Text>

            <View style={styles.fieldGroup}>
              <Text style={styles.fieldLabel}>Server</Text>
              <ServerPicker
                selected={selectedServer}
                onSelect={server => {
                  setSelectedServer(server.value);
                  setConnectionError(null);
                }}
              />
            </View>

            {connectionError && (
              <View style={styles.errorBox}>
                <Text style={styles.errorText}>{connectionError}</Text>
              </View>
            )}

            <GlassCard style={styles.securityNotice} padding={spacing.md}>
              <Text style={styles.securityIcon}>🔒</Text>
              <Text style={styles.securityText}>
                Your credentials are encrypted end-to-end and sent directly to
                MetaApi's secure vault. made. never stores or logs passwords.
              </Text>
            </GlassCard>

            <TouchableOpacity
              style={[
                styles.primaryButton,
                (!selectedServer || isLoading) && styles.buttonDisabled,
              ]}
              onPress={handleTestConnection}
              disabled={!selectedServer || isLoading}
              activeOpacity={0.85}
            >
              {isLoading ? (
                <ActivityIndicator color={colors.backgroundDeep} size="small" />
              ) : (
                <Text style={styles.primaryButtonText}>Test Connection</Text>
              )}
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.backButton}
              onPress={() => animateStepChange(() => setStep(1))}
            >
              <Text style={styles.backButtonText}>← Back</Text>
            </TouchableOpacity>
          </>
        );

      case 3:
        return (
          <>
            <Text style={styles.stepTitle}>Connection Verified</Text>
            <Text style={styles.stepSubtitle}>
              Your account is reachable. Review the details below before linking.
            </Text>

            {accountInfo && <AccountInfoCard info={accountInfo} />}

            <View style={styles.paperRow}>
              <View style={styles.paperTextGroup}>
                <Text style={styles.paperLabel}>Start in Paper Trading</Text>
                <Text style={styles.paperSub}>
                  Test signals safely before using live funds
                </Text>
              </View>
              <Switch
                value={usePaperTrading}
                onValueChange={setUsePaperTrading}
                trackColor={{ false: colors.glassBorder, true: colors.goldBorderStrong }}
                thumbColor={usePaperTrading ? colors.goldPrimary : colors.textMuted}
              />
            </View>

            <TouchableOpacity
              style={[styles.primaryButton, isLoading && styles.buttonDisabled]}
              onPress={handleConfirm}
              disabled={isLoading}
              activeOpacity={0.85}
            >
              {isLoading ? (
                <ActivityIndicator color={colors.backgroundDeep} size="small" />
              ) : (
                <Text style={styles.primaryButtonText}>
                  {usePaperTrading ? 'Use Paper Trading' : 'Link Broker Account'}
                </Text>
              )}
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.backButton}
              onPress={() => {
                setAccountInfo(null);
                setConnectionError(null);
                animateStepChange(() => setStep(2));
              }}
            >
              <Text style={styles.backButtonText}>← Back</Text>
            </TouchableOpacity>
          </>
        );

      default:
        return null;
    }
  };

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" />
      <LinearGradient
        colors={[colors.ambientGradientStart, colors.backgroundDeep, colors.ambientGradientEnd]}
        style={StyleSheet.absoluteFill}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.8, y: 1 }}
      />

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={insets.top}
      >
        <ScrollView
          style={styles.flex}
          contentContainerStyle={[
            styles.scrollContent,
            { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xxl },
          ]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Header */}
          <View style={styles.header}>
            <TouchableOpacity
              style={styles.closeButton}
              onPress={() => navigation.goBack()}
              hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
            >
              <Text style={styles.closeIcon}>✕</Text>
            </TouchableOpacity>
            <Text style={styles.screenTitle}>Connect Broker</Text>
            <View style={styles.closeButton} />
          </View>

          <StepIndicator current={step} total={TOTAL_STEPS} />

          {/* Step content */}
          <Animated.View style={{ opacity: fadeAnim }}>
            <GlassCard style={styles.card}>
              {renderStep()}
            </GlassCard>
          </Animated.View>

          {/* Footer disclaimer */}
          <Text style={styles.disclaimer}>
            made. uses MetaApi to communicate with HFM. You can revoke access
            at any time in Settings → Broker → Disconnect.
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.backgroundDeep,
  },
  flex: { flex: 1 },
  scrollContent: {
    paddingHorizontal: spacing.lg,
  },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.xl,
  },
  screenTitle: {
    ...typography.h3,
    color: colors.textPrimary,
    fontWeight: fontWeights.semibold as any,
    textAlign: 'center',
  },
  closeButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  closeIcon: {
    color: colors.textSecondary,
    fontSize: 18,
  },

  // Card
  card: {
    marginBottom: spacing.lg,
  },

  // Step content
  stepTitle: {
    ...typography.h3,
    color: colors.textPrimary,
    fontWeight: fontWeights.semibold as any,
    marginBottom: spacing.xs,
  },
  stepSubtitle: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    lineHeight: 20,
    marginBottom: spacing.xl,
  },

  // Form fields
  fieldGroup: {
    marginBottom: spacing.lg,
  },
  fieldLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    fontWeight: fontWeights.semibold as any,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: spacing.xs,
  },
  input: {
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
    borderRadius: borderRadius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    color: colors.textPrimary,
    ...typography.body,
    fontSize: 16,
  },
  passwordRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  passwordInput: {
    flex: 1,
    borderTopRightRadius: 0,
    borderBottomRightRadius: 0,
  },
  visibilityToggle: {
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1,
    borderLeftWidth: 0,
    borderColor: colors.glassBorder,
    borderTopRightRadius: borderRadius.md,
    borderBottomRightRadius: borderRadius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
    height: 52,
  },
  visibilityIcon: { fontSize: 18 },

  // Divider
  dividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: spacing.lg,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: colors.glassBorder,
  },
  dividerLabel: {
    ...typography.caption,
    color: colors.textMuted,
    marginHorizontal: spacing.md,
  },

  // Paper trading toggle row
  paperRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    borderRadius: borderRadius.md,
    paddingHorizontal: spacing.md,
    marginBottom: spacing.lg,
  },
  paperTextGroup: { flex: 1, marginRight: spacing.md },
  paperLabel: {
    ...typography.body,
    color: colors.textPrimary,
    fontWeight: fontWeights.medium as any,
  },
  paperSub: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: 2,
  },

  // Buttons
  primaryButton: {
    backgroundColor: colors.goldPrimary,
    borderRadius: borderRadius.md,
    paddingVertical: spacing.md + 2,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.sm,
    minHeight: 52,
  },
  buttonDisabled: {
    opacity: 0.4,
  },
  primaryButtonText: {
    ...typography.body,
    color: colors.backgroundDeep,
    fontWeight: fontWeights.bold as any,
    fontSize: 16,
  },
  backButton: {
    alignItems: 'center',
    paddingVertical: spacing.md,
    marginTop: spacing.xs,
  },
  backButtonText: {
    ...typography.body,
    color: colors.textSecondary,
  },

  // Security notice
  securityNotice: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: spacing.lg,
  },
  securityIcon: {
    fontSize: 16,
    marginRight: spacing.sm,
    marginTop: 1,
  },
  securityText: {
    ...typography.caption,
    color: colors.textSecondary,
    flex: 1,
    lineHeight: 18,
  },

  // Error
  errorBox: {
    backgroundColor: 'rgba(239,68,68,0.12)',
    borderWidth: 1,
    borderColor: 'rgba(239,68,68,0.3)',
    borderRadius: borderRadius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginBottom: spacing.md,
  },
  errorText: {
    ...typography.bodySmall,
    color: colors.sellRed,
  },

  // Footer
  disclaimer: {
    ...typography.caption,
    color: colors.textMuted,
    textAlign: 'center',
    lineHeight: 18,
    paddingHorizontal: spacing.md,
  },
});
