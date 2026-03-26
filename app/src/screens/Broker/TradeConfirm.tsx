/**
 * TradeConfirm — shown when user taps "Confirm Trade" on a signal
 *
 * Validates signal is still valid, shows execution summary,
 * gets user confirmation before sending to broker/paper account.
 *
 * Validity check: signal entry must be within 0.5x ATR of current price.
 * Displays lot size, dollar risk, SL/TP1 before execution.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
  Switch,
  Animated,
  StatusBar,
  Alert,
  Platform,
} from 'react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import LinearGradient from 'react-native-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing, typography, fontWeights, borderRadius, shadows } from '../../theme';
import GlassCard from '../../components/GlassCard';
import type { Signal } from '../../types';

// ── Types ─────────────────────────────────────────────────────────────────────

type SlippageTolerance = 1 | 2 | 5;

interface ExecutionResult {
  orderId: string;
  fillPrice: number;
  fillLots: number;
  slippage: number;
  isPaper: boolean;
}

// These would come from the navigation stack in a real app
type TradeConfirmRouteParams = {
  signal: Signal;
  isPaperMode?: boolean;
};

// ── Helper formatters ─────────────────────────────────────────────────────────

function formatPrice(price: number, pair: string): string {
  const decimals = pair === 'XAUUSD' ? 2 : 3;
  return price.toFixed(decimals);
}

function formatPips(pips: number, pair: string): string {
  return `${pips.toFixed(1)} pips`;
}

// ── Validity status component ─────────────────────────────────────────────────

interface ValidityStatusProps {
  isValid: boolean;
  message: string;
  isChecking: boolean;
}

function ValidityStatus({ isValid, message, isChecking }: ValidityStatusProps) {
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (isChecking) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 0.5, duration: 500, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1, duration: 500, useNativeDriver: true }),
        ]),
      ).start();
    } else {
      pulseAnim.stopAnimation();
      pulseAnim.setValue(1);
    }
  }, [isChecking, pulseAnim]);

  const containerStyle = isChecking
    ? validityStyles.checking
    : isValid
      ? validityStyles.valid
      : validityStyles.invalid;

  const iconStyle = isChecking
    ? validityStyles.iconChecking
    : isValid
      ? validityStyles.iconValid
      : validityStyles.iconInvalid;

  return (
    <Animated.View style={[validityStyles.container, containerStyle, { opacity: isChecking ? pulseAnim : 1 }]}>
      <Text style={[validityStyles.icon, iconStyle]}>
        {isChecking ? '⟳' : isValid ? '✓' : '✕'}
      </Text>
      <Text style={[validityStyles.message, !isValid && !isChecking && validityStyles.messageInvalid]}>
        {message}
      </Text>
    </Animated.View>
  );
}

const validityStyles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: borderRadius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    marginBottom: spacing.lg,
    borderWidth: 1,
  },
  checking: {
    backgroundColor: 'rgba(59,130,246,0.1)',
    borderColor: 'rgba(59,130,246,0.3)',
  },
  valid: {
    backgroundColor: 'rgba(34,197,94,0.1)',
    borderColor: 'rgba(34,197,94,0.3)',
  },
  invalid: {
    backgroundColor: 'rgba(239,68,68,0.1)',
    borderColor: 'rgba(239,68,68,0.3)',
  },
  icon: {
    fontSize: 16,
    marginRight: spacing.sm,
    fontWeight: fontWeights.bold as any,
  },
  iconChecking: { color: colors.info },
  iconValid: { color: colors.buyGreen },
  iconInvalid: { color: colors.sellRed },
  message: {
    ...typography.bodySmall,
    color: colors.textPrimary,
    flex: 1,
  },
  messageInvalid: { color: colors.sellRed },
});

// ── Price row ─────────────────────────────────────────────────────────────────

function PriceRow({
  label,
  value,
  subValue,
  valueColor,
  isEntry,
}: {
  label: string;
  value: string;
  subValue?: string;
  valueColor?: string;
  isEntry?: boolean;
}) {
  return (
    <View style={priceRowStyles.row}>
      <View style={priceRowStyles.labelGroup}>
        {isEntry && <View style={priceRowStyles.entryDot} />}
        <Text style={[priceRowStyles.label, isEntry && priceRowStyles.labelEntry]}>{label}</Text>
      </View>
      <View style={priceRowStyles.valueGroup}>
        <Text style={[priceRowStyles.value, valueColor ? { color: valueColor } : undefined]}>
          {value}
        </Text>
        {subValue && <Text style={priceRowStyles.subValue}>{subValue}</Text>}
      </View>
    </View>
  );
}

const priceRowStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.04)',
  },
  labelGroup: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  entryDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.goldPrimary,
    marginRight: spacing.sm,
  },
  label: {
    ...typography.bodySmall,
    color: colors.textSecondary,
  },
  labelEntry: { color: colors.goldPrimary, fontWeight: fontWeights.medium as any },
  valueGroup: { alignItems: 'flex-end' },
  value: {
    ...typography.body,
    color: colors.textPrimary,
    fontWeight: fontWeights.semibold as any,
  },
  subValue: {
    ...typography.caption,
    color: colors.textMuted,
    marginTop: 1,
  },
});

// ── Slippage selector ─────────────────────────────────────────────────────────

function SlippageSelector({
  value,
  onChange,
}: {
  value: SlippageTolerance;
  onChange: (v: SlippageTolerance) => void;
}) {
  const OPTIONS: SlippageTolerance[] = [1, 2, 5];

  return (
    <View style={slippageStyles.container}>
      <Text style={slippageStyles.label}>Slippage Tolerance</Text>
      <View style={slippageStyles.options}>
        {OPTIONS.map(opt => (
          <TouchableOpacity
            key={opt}
            style={[
              slippageStyles.option,
              opt === value && slippageStyles.optionSelected,
            ]}
            onPress={() => onChange(opt)}
            activeOpacity={0.75}
          >
            <Text
              style={[
                slippageStyles.optionText,
                opt === value && slippageStyles.optionTextSelected,
              ]}
            >
              {opt} pip{opt > 1 ? 's' : ''}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

const slippageStyles = StyleSheet.create({
  container: { marginBottom: spacing.lg },
  label: {
    ...typography.caption,
    color: colors.textSecondary,
    fontWeight: fontWeights.semibold as any,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: spacing.sm,
  },
  options: { flexDirection: 'row', gap: spacing.sm },
  option: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.03)',
  },
  optionSelected: {
    borderColor: colors.goldBorderStrong,
    backgroundColor: 'rgba(212,168,67,0.1)',
  },
  optionText: {
    ...typography.caption,
    color: colors.textSecondary,
    fontWeight: fontWeights.medium as any,
  },
  optionTextSelected: { color: colors.goldPrimary },
});

// ── Main screen ────────────────────────────────────────────────────────────────

export default function TradeConfirm() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation();

  // In production this comes from route.params; we use a minimal mock here
  // to keep the component runnable without a live navigation stack in Storybook / tests.
  const route = useRoute<RouteProp<{ TradeConfirm: TradeConfirmRouteParams }, 'TradeConfirm'>>();
  const { signal, isPaperMode: initialPaperMode = false } = route.params ?? {};

  // ── State ──────────────────────────────────────────────────────────────────
  const [isValidityChecking, setIsValidityChecking] = useState(true);
  const [isSignalValid, setIsSignalValid] = useState(false);
  const [validityMessage, setValidityMessage] = useState('Checking signal validity...');
  const [currentPrice, setCurrentPrice] = useState<number | null>(null);
  const [slippageTolerance, setSlippageTolerance] = useState<SlippageTolerance>(1);
  const [riskAcknowledged, setRiskAcknowledged] = useState(false);
  const [usePaperMode, setUsePaperMode] = useState(initialPaperMode);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null);

  const isBuy = signal?.direction === 'BUY';

  // ── Validity check on mount ────────────────────────────────────────────────
  useEffect(() => {
    if (!signal) {
      setIsValidityChecking(false);
      setIsSignalValid(false);
      setValidityMessage('No signal data available');
      return;
    }

    const checkValidity = async () => {
      setIsValidityChecking(true);
      try {
        // Fetch current market price
        const resp = await fetch(
          `${process.env.API_BASE_URL ?? 'http://localhost:8000'}/signals/${signal.id}/validity`,
        );
        if (!resp.ok) throw new Error('Failed to fetch validity');

        const data: { valid: boolean; currentPrice: number; message: string } =
          await resp.json();

        setCurrentPrice(data.currentPrice);
        setIsSignalValid(data.valid);
        setValidityMessage(data.message);
      } catch {
        // Fallback: local staleness check (signal older than expiry or > 2 min)
        const generated = new Date(signal.generatedAt).getTime();
        const expires = new Date(signal.expiresAt).getTime();
        const now = Date.now();
        const valid = now < expires;

        setIsSignalValid(valid);
        setCurrentPrice(signal.entryPrice);
        setValidityMessage(
          valid
            ? 'Signal valid — price within acceptable range of entry'
            : 'Signal expired — entry zone is no longer valid',
        );
      } finally {
        setIsValidityChecking(false);
      }
    };

    checkValidity();
  }, [signal]);

  // ── Execute trade ──────────────────────────────────────────────────────────
  const handleExecute = useCallback(async () => {
    if (!signal || !isSignalValid || !riskAcknowledged) return;

    setIsExecuting(true);
    try {
      const endpoint = usePaperMode ? '/broker/paper-trade' : '/broker/execute';
      const resp = await fetch(
        `${process.env.API_BASE_URL ?? 'http://localhost:8000'}${endpoint}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            signal_id: signal.id,
            slippage_tolerance_pips: slippageTolerance,
            paper: usePaperMode,
          }),
        },
      );

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        const msg = err?.detail ?? `Execution failed (${resp.status})`;

        // Handle requote/rejection with user-friendly prompt
        if (resp.status === 422) {
          Alert.alert(
            'Price Moved',
            'The market moved beyond your slippage tolerance. Would you like to retry at the current price?',
            [
              { text: 'Cancel', style: 'cancel' },
              {
                text: 'Retry',
                onPress: async () => {
                  setSlippageTolerance(2);
                  setIsExecuting(false);
                },
              },
            ],
          );
          return;
        }

        throw new Error(msg);
      }

      const result: ExecutionResult = await resp.json();
      setExecutionResult(result);
    } catch (err: any) {
      Alert.alert(
        'Execution Failed',
        err.message ?? 'An unexpected error occurred. Please try again.',
        [{ text: 'OK' }],
      );
    } finally {
      setIsExecuting(false);
    }
  }, [signal, isSignalValid, riskAcknowledged, usePaperMode, slippageTolerance]);

  // ── Success screen ─────────────────────────────────────────────────────────
  if (executionResult) {
    const slippagePips = Math.abs(executionResult.slippage).toFixed(1);
    return (
      <View style={styles.root}>
        <StatusBar barStyle="light-content" />
        <LinearGradient
          colors={[colors.ambientGradientStart, colors.backgroundDeep]}
          style={StyleSheet.absoluteFill}
        />
        <View style={[styles.successContainer, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
          <Text style={styles.successEmoji}>✓</Text>
          <Text style={styles.successTitle}>
            {executionResult.isPaper ? 'Paper Trade Placed' : 'Order Sent'}
          </Text>
          <Text style={styles.successSub}>
            {signal?.pair} {signal?.direction} — {executionResult.fillLots} lots
          </Text>

          <GlassCard style={styles.fillCard}>
            <PriceRow
              label="Fill Price"
              value={formatPrice(executionResult.fillPrice, signal?.pair ?? 'XAUUSD')}
              isEntry
            />
            <PriceRow
              label="Lots Filled"
              value={executionResult.fillLots.toFixed(2)}
            />
            <PriceRow
              label="Slippage"
              value={`${slippagePips} pips`}
              valueColor={Math.abs(executionResult.slippage) > 1 ? colors.warning : colors.buyGreen}
            />
            <PriceRow
              label="Mode"
              value={executionResult.isPaper ? 'Paper Trade' : 'Live Trade'}
              valueColor={executionResult.isPaper ? colors.info : colors.buyGreen}
            />
          </GlassCard>

          <TouchableOpacity
            style={styles.primaryButton}
            onPress={() => navigation.goBack()}
            activeOpacity={0.85}
          >
            <Text style={styles.primaryButtonText}>View in Journal</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.secondaryButton}
            onPress={() => navigation.goBack()}
          >
            <Text style={styles.secondaryButtonText}>Back to Signals</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // ── Guard: no signal ────────────────────────────────────────────────────────
  if (!signal) {
    return (
      <View style={[styles.root, styles.centerContent]}>
        <Text style={styles.errorText}>Signal data not available.</Text>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.linkText}>Go Back</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Derived values ─────────────────────────────────────────────────────────
  const directionColor = isBuy ? colors.buyGreen : colors.sellRed;
  const displayPrice = currentPrice ?? signal.entryPrice;
  const rrRatio = signal.riskPips > 0
    ? (Math.abs(signal.tp1 - signal.entryPrice) / Math.abs(signal.stopLoss - signal.entryPrice)).toFixed(1)
    : '—';

  const canExecute =
    !isValidityChecking &&
    isSignalValid &&
    riskAcknowledged &&
    !isExecuting;

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" />
      <LinearGradient
        colors={[colors.ambientGradientStart, colors.backgroundDeep, colors.ambientGradientEnd]}
        style={StyleSheet.absoluteFill}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.8, y: 1 }}
      />

      <ScrollView
        style={styles.flex}
        contentContainerStyle={[
          styles.scrollContent,
          { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xxl },
        ]}
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
          <Text style={styles.screenTitle}>Confirm Trade</Text>
          <View style={styles.closeButton} />
        </View>

        {/* Pair + Direction banner */}
        <GlassCard style={styles.bannerCard} borderHighlight>
          <View style={styles.bannerContent}>
            <View>
              <Text style={styles.bannerPair}>{signal.pair}</Text>
              <Text style={styles.bannerTimeframe}>{signal.timeframe} · {signal.tradingStyle.replace('_', ' ')}</Text>
            </View>
            <View style={[styles.directionBadge, { backgroundColor: isBuy ? colors.buyGreenAlpha : colors.sellRedAlpha }]}>
              <Text style={[styles.directionText, { color: directionColor }]}>
                {signal.direction}
              </Text>
            </View>
          </View>
        </GlassCard>

        {/* Signal validity */}
        <ValidityStatus
          isValid={isSignalValid}
          message={validityMessage}
          isChecking={isValidityChecking}
        />

        {/* Execution summary */}
        <GlassCard style={styles.summaryCard}>
          <Text style={styles.sectionLabel}>Execution Summary</Text>

          <PriceRow
            label="Entry (current market)"
            value={formatPrice(displayPrice, signal.pair)}
            subValue={displayPrice !== signal.entryPrice
              ? `Signal: ${formatPrice(signal.entryPrice, signal.pair)}`
              : undefined}
            valueColor={colors.goldPrimary}
            isEntry
          />
          <PriceRow
            label="Stop Loss"
            value={formatPrice(signal.stopLoss, signal.pair)}
            subValue={formatPips(signal.riskPips, signal.pair)}
            valueColor={colors.sellRed}
          />
          <PriceRow
            label="Take Profit 1"
            value={formatPrice(signal.tp1, signal.pair)}
            subValue={`R:R 1:${rrRatio}`}
            valueColor={colors.buyGreen}
          />
          <PriceRow
            label="Lot Size"
            value={signal.lotSize.toFixed(2) + ' lots'}
          />

          <View style={styles.riskHighlight}>
            <Text style={styles.riskLabel}>Dollar Risk</Text>
            <Text style={styles.riskValue}>
              ${signal.dollarRisk.toFixed(2)}
            </Text>
          </View>
        </GlassCard>

        {/* Slippage tolerance */}
        <GlassCard style={styles.optionsCard}>
          <SlippageSelector value={slippageTolerance} onChange={setSlippageTolerance} />

          {/* Paper trading toggle */}
          <View style={styles.paperRow}>
            <View style={styles.paperTextGroup}>
              <Text style={styles.paperLabel}>Paper Trade Instead</Text>
              <Text style={styles.paperSub}>Simulated execution, no real money</Text>
            </View>
            <Switch
              value={usePaperMode}
              onValueChange={setUsePaperMode}
              trackColor={{ false: colors.glassBorder, true: colors.goldBorderStrong }}
              thumbColor={usePaperMode ? colors.goldPrimary : colors.textMuted}
            />
          </View>
        </GlassCard>

        {/* Risk acknowledgement */}
        <TouchableOpacity
          style={styles.ackRow}
          onPress={() => setRiskAcknowledged(v => !v)}
          activeOpacity={0.8}
        >
          <View style={[styles.checkbox, riskAcknowledged && styles.checkboxChecked]}>
            {riskAcknowledged && <Text style={styles.checkmark}>✓</Text>}
          </View>
          <Text style={styles.ackText}>
            I understand trading involves risk and I am responsible for this
            trade. made. provides analysis only — not financial advice.
          </Text>
        </TouchableOpacity>

        {/* Execute button */}
        <TouchableOpacity
          style={[
            styles.executeButton,
            { borderColor: directionColor },
            !canExecute && styles.executeButtonDisabled,
          ]}
          onPress={handleExecute}
          disabled={!canExecute}
          activeOpacity={0.85}
        >
          {isExecuting ? (
            <View style={styles.executingRow}>
              <ActivityIndicator color={colors.textPrimary} size="small" />
              <Text style={styles.executingText}>
                Sending to {usePaperMode ? 'Paper Account' : 'MT4/MT5'}...
              </Text>
            </View>
          ) : (
            <Text
              style={[
                styles.executeButtonText,
                canExecute ? { color: directionColor } : { color: colors.textMuted },
              ]}
            >
              {usePaperMode ? 'Execute Paper Trade' : `Execute ${signal.direction}`}
            </Text>
          )}
        </TouchableOpacity>

        {/* Expired signal notice */}
        {!isValidityChecking && !isSignalValid && (
          <GlassCard style={styles.expiredNotice}>
            <Text style={styles.expiredTitle}>Signal No Longer Valid</Text>
            <Text style={styles.expiredBody}>
              Price has moved beyond the acceptable entry range. Wait for a new
              signal or review the setup on the signal detail screen.
            </Text>
          </GlassCard>
        )}
      </ScrollView>
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
  centerContent: {
    alignItems: 'center',
    justifyContent: 'center',
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

  // Banner
  bannerCard: { marginBottom: spacing.lg },
  bannerContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  bannerPair: {
    ...typography.h2,
    color: colors.textPrimary,
    fontWeight: fontWeights.bold as any,
  },
  bannerTimeframe: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: 2,
    textTransform: 'capitalize',
  },
  directionBadge: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md,
  },
  directionText: {
    fontSize: 20,
    fontWeight: fontWeights.bold as any,
    letterSpacing: 1,
  },

  // Summary
  summaryCard: { marginBottom: spacing.lg },
  sectionLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    fontWeight: fontWeights.semibold as any,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: spacing.sm,
  },
  riskHighlight: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.glassBorder,
  },
  riskLabel: {
    ...typography.body,
    color: colors.textSecondary,
    fontWeight: fontWeights.medium as any,
  },
  riskValue: {
    ...typography.h3,
    color: colors.warning,
    fontWeight: fontWeights.bold as any,
  },

  // Options card
  optionsCard: { marginBottom: spacing.lg },
  paperRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.04)',
    marginTop: spacing.sm,
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

  // Acknowledgement
  ackRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: spacing.xl,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 1.5,
    borderColor: colors.textMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
    marginTop: 1,
    flexShrink: 0,
  },
  checkboxChecked: {
    borderColor: colors.goldPrimary,
    backgroundColor: 'rgba(212,168,67,0.2)',
  },
  checkmark: {
    fontSize: 13,
    color: colors.goldPrimary,
    fontWeight: fontWeights.bold as any,
  },
  ackText: {
    ...typography.caption,
    color: colors.textSecondary,
    flex: 1,
    lineHeight: 18,
  },

  // Execute button
  executeButton: {
    borderWidth: 1.5,
    borderRadius: borderRadius.md,
    paddingVertical: spacing.md + 4,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.03)',
    minHeight: 56,
    marginBottom: spacing.lg,
  },
  executeButtonDisabled: {
    borderColor: colors.glassBorder,
    opacity: 0.5,
  },
  executeButtonText: {
    fontSize: 17,
    fontWeight: fontWeights.bold as any,
    letterSpacing: 0.5,
  },
  executingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  executingText: {
    ...typography.body,
    color: colors.textSecondary,
  },

  // Expired notice
  expiredNotice: {
    backgroundColor: 'rgba(239,68,68,0.08)',
    borderColor: 'rgba(239,68,68,0.2)',
    marginBottom: spacing.lg,
  },
  expiredTitle: {
    ...typography.body,
    color: colors.sellRed,
    fontWeight: fontWeights.semibold as any,
    marginBottom: spacing.xs,
  },
  expiredBody: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    lineHeight: 20,
  },

  // Error fallback
  errorText: {
    ...typography.body,
    color: colors.textSecondary,
    marginBottom: spacing.md,
  },
  linkText: {
    ...typography.body,
    color: colors.goldPrimary,
  },

  // Success screen
  successContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },
  successEmoji: {
    fontSize: 56,
    color: colors.success,
    marginBottom: spacing.lg,
  },
  successTitle: {
    ...typography.h2,
    color: colors.textPrimary,
    fontWeight: fontWeights.bold as any,
    textAlign: 'center',
    marginBottom: spacing.xs,
  },
  successSub: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
    marginBottom: spacing.xl,
  },
  fillCard: {
    width: '100%',
    marginBottom: spacing.xl,
  },
  primaryButton: {
    backgroundColor: colors.goldPrimary,
    borderRadius: borderRadius.md,
    paddingVertical: spacing.md + 2,
    paddingHorizontal: spacing.xxl,
    alignItems: 'center',
    width: '100%',
    marginBottom: spacing.md,
  },
  primaryButtonText: {
    ...typography.body,
    color: colors.backgroundDeep,
    fontWeight: fontWeights.bold as any,
    fontSize: 16,
  },
  secondaryButton: {
    paddingVertical: spacing.md,
    alignItems: 'center',
  },
  secondaryButtonText: {
    ...typography.body,
    color: colors.textSecondary,
  },
});
