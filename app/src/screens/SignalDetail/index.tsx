import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Animated,
  StatusBar,
  Alert,
} from 'react-native';
import { useRoute, useNavigation, RouteProp } from '@react-navigation/native';
import { useQuery } from '@tanstack/react-query';
import LinearGradient from 'react-native-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing, typography, fontWeights, borderRadius, shadows } from '../../theme';
import { signals as signalsApi } from '../../services/api';
import { useUIMode } from '../../store';
import GlassCard from '../../components/GlassCard';
import ConfidenceRing from '../../components/ConfidenceRing';
import ModuleDissent from '../../components/ModuleDissent';
import RegimeBadge from '../../components/RegimeBadge';
import CountdownTimer from '../../components/CountdownTimer';
import PairFlag from '../../components/PairFlag';
import type { HomeStackParamList } from '../../navigation/types';
import type { Signal } from '../../types';

type RouteType = RouteProp<HomeStackParamList, 'SignalDetail'>;

function PriceLevelVisualizer({ signal }: { signal: Signal }) {
  const isBuy = signal.direction === 'BUY';

  // Sort prices for visual display
  const prices = isBuy
    ? [signal.tp3, signal.tp2, signal.tp1, signal.entryPrice, signal.stopLoss]
    : [signal.stopLoss, signal.entryPrice, signal.tp1, signal.tp2, signal.tp3];

  const max = Math.max(...prices);
  const min = Math.min(...prices);
  const range = max - min || 1;

  const getPercent = (price: number) => ((price - min) / range) * 100;

  const levels = isBuy
    ? [
        { label: 'TP3', price: signal.tp3, color: colors.buyGreen, opacity: 0.6 },
        { label: 'TP2', price: signal.tp2, color: colors.buyGreen, opacity: 0.75 },
        { label: 'TP1', price: signal.tp1, color: colors.buyGreen, opacity: 1 },
        { label: 'Entry', price: signal.entryPrice, color: colors.goldPrimary, opacity: 1 },
        { label: 'SL', price: signal.stopLoss, color: colors.sellRed, opacity: 1 },
      ]
    : [
        { label: 'SL', price: signal.stopLoss, color: colors.sellRed, opacity: 1 },
        { label: 'Entry', price: signal.entryPrice, color: colors.goldPrimary, opacity: 1 },
        { label: 'TP1', price: signal.tp1, color: colors.buyGreen, opacity: 1 },
        { label: 'TP2', price: signal.tp2, color: colors.buyGreen, opacity: 0.75 },
        { label: 'TP3', price: signal.tp3, color: colors.buyGreen, opacity: 0.6 },
      ];

  return (
    <View style={vizStyles.container}>
      <View style={vizStyles.track}>
        {levels.map((level) => {
          const pct = getPercent(level.price);
          return (
            <View
              key={level.label}
              style={[vizStyles.marker, { bottom: `${pct}%` as any }]}
            >
              <View style={[vizStyles.line, { backgroundColor: level.color, opacity: level.opacity }]} />
              <Text style={[vizStyles.markerLabel, { color: level.color }]}>{level.label}</Text>
              <Text style={[vizStyles.markerPrice, { color: level.color, opacity: level.opacity }]}>
                {level.price.toFixed(signal.pair === 'XAUUSD' ? 2 : 3)}
              </Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

const vizStyles = StyleSheet.create({
  container: {
    height: 200,
    marginVertical: spacing.md,
  },
  track: {
    flex: 1,
    borderLeftWidth: 2,
    borderLeftColor: colors.glassBorder,
    marginLeft: 60,
    position: 'relative',
  },
  marker: {
    position: 'absolute',
    left: 0,
    right: 0,
    flexDirection: 'row',
    alignItems: 'center',
  },
  line: {
    width: 16,
    height: 2,
    marginLeft: -8,
  },
  markerLabel: {
    fontSize: 11,
    fontWeight: fontWeights.semibold,
    marginLeft: spacing.sm,
    width: 30,
  },
  markerPrice: {
    fontSize: 12,
    fontWeight: fontWeights.medium,
    marginLeft: spacing.xs,
  },
});

export default function SignalDetailScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation();
  const insets = useSafeAreaInsets();
  const { isSimpleMode, isProMode, isMaxMode } = useUIMode();
  const [showTooltip, setShowTooltip] = useState<string | null>(null);
  const fadeAnim = useRef(new Animated.Value(0)).current;

  const { data: signal, isLoading } = useQuery({
    queryKey: ['signal', route.params.signalId],
    queryFn: () => signalsApi.getSignal(route.params.signalId),
    staleTime: 10_000,
  });

  useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, [fadeAnim]);

  if (isLoading || !signal) {
    return (
      <View style={styles.loading}>
        <Text style={styles.loadingText}>Loading signal...</Text>
      </View>
    );
  }

  const isBuy = signal.direction === 'BUY';
  const accentColor = isBuy ? colors.buyGreen : colors.sellRed;

  const rr = (tp2: number, entry: number, sl: number, dir: string): string => {
    const risk = Math.abs(entry - sl);
    const reward = Math.abs(tp2 - entry);
    if (risk === 0) return '–';
    return `1:${(reward / risk).toFixed(1)}`;
  };

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" />
      <LinearGradient
        colors={[colors.backgroundDeep, colors.ambientGradientEnd, colors.backgroundDeep]}
        style={StyleSheet.absoluteFill}
      />

      {/* Back button */}
      <TouchableOpacity
        style={[styles.backBtn, { top: insets.top + 8 }]}
        onPress={() => navigation.goBack()}
      >
        <Text style={styles.backIcon}>←</Text>
        <Text style={styles.backText}>Signals</Text>
      </TouchableOpacity>

      <Animated.ScrollView
        style={{ opacity: fadeAnim }}
        contentContainerStyle={[
          styles.scrollContent,
          { paddingTop: insets.top + 60, paddingBottom: insets.bottom + 24 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Header card */}
        <GlassCard style={styles.headerCard} borderHighlight>
          <View style={styles.headerTop}>
            <PairFlag pair={signal.pair} size="lg" />
            <ConfidenceRing score={signal.decayedScore} size={72} />
          </View>

          <View style={[styles.dirBadge, { backgroundColor: `${accentColor}22`, borderColor: accentColor }]}>
            <Text style={[styles.dirText, { color: accentColor }]}>{signal.direction}</Text>
          </View>

          <View style={styles.metaRow}>
            <RegimeBadge regime={signal.regime} />
            {signal.hasNewsRisk && (
              <View style={styles.newsBadge}>
                <Text style={styles.newsBadgeText}>NEWS RISK</Text>
              </View>
            )}
            {signal.hasHTFConflict && (
              <View style={styles.conflictBadge}>
                <Text style={styles.conflictBadgeText}>HTF CONFLICT</Text>
              </View>
            )}
            {!isSimpleMode && (
              <CountdownTimer targetTime={signal.expiresAt} label="Expires" />
            )}
          </View>

          {signal.hasHTFConflict && signal.htfConflictDescription && (
            <View style={styles.conflictDesc}>
              <Text style={styles.conflictDescText}>{signal.htfConflictDescription}</Text>
            </View>
          )}
        </GlassCard>

        {/* Price levels */}
        <GlassCard style={styles.card}>
          <Text style={styles.sectionTitle}>Price Levels</Text>
          <PriceLevelVisualizer signal={signal} />

          <View style={styles.levelsGrid}>
            {[
              { label: 'Entry', value: signal.entryPrice, color: colors.goldPrimary },
              { label: 'Stop Loss', value: signal.stopLoss, color: colors.sellRed },
              { label: 'TP1 (40%)', value: signal.tp1, color: colors.buyGreen },
              { label: 'TP2 (30%)', value: signal.tp2, color: colors.buyGreen },
              { label: 'TP3 (30%)', value: signal.tp3, color: colors.buyGreen },
              { label: 'R:R (TP2)', value: rr(signal.tp2, signal.entryPrice, signal.stopLoss, signal.direction), color: colors.goldLight, isText: true },
            ].map((item) => (
              <View key={item.label} style={styles.levelCell}>
                <Text style={styles.levelLabel}>{item.label}</Text>
                <Text style={[styles.levelValue, { color: item.color }]}>
                  {item.isText
                    ? String(item.value)
                    : (item.value as number).toFixed(signal.pair === 'XAUUSD' ? 2 : 3)}
                </Text>
              </View>
            ))}
          </View>
        </GlassCard>

        {/* Risk */}
        <GlassCard style={styles.card}>
          <Text style={styles.sectionTitle}>Risk Summary</Text>
          <View style={styles.riskRow}>
            <RiskItem label="Lot Size" value={`${signal.lotSize.toFixed(2)} lots`} />
            <RiskItem label="Dollar Risk" value={`$${signal.dollarRisk.toFixed(2)}`} />
            <RiskItem label="Risk Pips" value={`${signal.riskPips.toFixed(1)}`} />
          </View>
        </GlassCard>

        {/* Rationale */}
        {signal.rationale && (
          <GlassCard style={styles.card}>
            <Text style={styles.sectionTitle}>Setup Rationale</Text>
            <Text style={styles.rationaleText}>{signal.rationale}</Text>
          </GlassCard>
        )}

        {/* Module dissent (Pro/Max) */}
        {!isSimpleMode && signal.dissent && signal.dissent.length > 0 && (
          <GlassCard style={styles.card}>
            <Text style={styles.sectionTitle}>Module Alignment</Text>
            <ModuleDissent modules={signal.dissent} />
          </GlassCard>
        )}

        {/* Raw scores (Max) */}
        {isMaxMode && signal.moduleScores && (
          <GlassCard style={styles.card}>
            <Text style={styles.sectionTitle}>Raw Module Scores</Text>
            {Object.entries(signal.moduleScores).map(([mod, score]) => (
              <View key={mod} style={styles.rawScoreRow}>
                <Text style={styles.rawScoreLabel}>{mod.replace(/_/g, ' ')}</Text>
                <Text style={[
                  styles.rawScoreValue,
                  { color: score > 0 ? colors.buyGreen : score < 0 ? colors.sellRed : colors.textMuted }
                ]}>
                  {score > 0 ? '+' : ''}{score.toFixed(2)}
                </Text>
              </View>
            ))}
          </GlassCard>
        )}

        {/* Actions */}
        <View style={styles.actions}>
          <TouchableOpacity
            style={[styles.confirmBtn, { backgroundColor: accentColor }]}
            onPress={() => Alert.alert('Broker Integration', 'Connect your HFM MT4/MT5 account in Settings to execute trades.')}
          >
            <Text style={styles.confirmBtnText}>Confirm Trade</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.alertBtn}
            onPress={() => Alert.alert('Alert Set', 'You will be notified when price approaches entry.')}
          >
            <Text style={styles.alertBtnText}>Set Alert</Text>
          </TouchableOpacity>
        </View>
      </Animated.ScrollView>
    </View>
  );
}

function RiskItem({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.riskItem}>
      <Text style={styles.riskItemLabel}>{label}</Text>
      <Text style={styles.riskItemValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.backgroundDeep },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.backgroundDeep },
  loadingText: { color: colors.textSecondary },
  backBtn: {
    position: 'absolute',
    left: spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    zIndex: 10,
    padding: spacing.sm,
  },
  backIcon: { color: colors.goldPrimary, fontSize: 18, fontWeight: fontWeights.semibold },
  backText: { color: colors.goldPrimary, fontSize: 16, fontWeight: fontWeights.medium },
  scrollContent: {
    paddingHorizontal: spacing.lg,
    gap: spacing.md,
  },
  headerCard: { marginBottom: 0 },
  headerTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  dirBadge: {
    borderRadius: borderRadius.lg,
    borderWidth: 2,
    paddingHorizontal: spacing.xxl,
    paddingVertical: spacing.md,
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  dirText: { fontSize: 32, fontWeight: fontWeights.bold, letterSpacing: 3 },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    alignItems: 'center',
  },
  newsBadge: {
    backgroundColor: 'rgba(245,158,11,0.15)',
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.warning,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  newsBadgeText: { color: colors.warning, fontSize: 10, fontWeight: fontWeights.bold, letterSpacing: 0.5 },
  conflictBadge: {
    backgroundColor: 'rgba(239,68,68,0.15)',
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.sellRed,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  conflictBadgeText: { color: colors.sellRed, fontSize: 10, fontWeight: fontWeights.bold, letterSpacing: 0.5 },
  conflictDesc: {
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: 'rgba(239,68,68,0.06)',
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: 'rgba(239,68,68,0.15)',
  },
  conflictDescText: { color: colors.textSecondary, fontSize: 13, lineHeight: 20 },
  card: { marginBottom: 0 },
  sectionTitle: {
    ...typography.headingSmall,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  levelsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  levelCell: {
    width: '30%',
    flexGrow: 1,
    backgroundColor: 'rgba(255,255,255,0.03)',
    borderRadius: borderRadius.sm,
    padding: spacing.sm,
  },
  levelLabel: {
    color: colors.textSecondary,
    fontSize: 11,
    fontWeight: fontWeights.medium,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  levelValue: { fontSize: 15, fontWeight: fontWeights.semibold },
  riskRow: { flexDirection: 'row', gap: spacing.sm },
  riskItem: {
    flex: 1,
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderRadius: borderRadius.md,
    padding: spacing.md,
    alignItems: 'center',
  },
  riskItemLabel: { color: colors.textSecondary, fontSize: 11, fontWeight: fontWeights.medium, marginBottom: 4 },
  riskItemValue: { color: colors.textPrimary, fontSize: 16, fontWeight: fontWeights.bold },
  rationaleText: { color: colors.textSecondary, fontSize: 14, lineHeight: 22 },
  rawScoreRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: colors.glassBorder,
  },
  rawScoreLabel: { color: colors.textSecondary, fontSize: 13, textTransform: 'capitalize' },
  rawScoreValue: { fontSize: 13, fontWeight: fontWeights.semibold },
  actions: { gap: spacing.sm, marginTop: spacing.sm },
  confirmBtn: {
    paddingVertical: spacing.lg,
    borderRadius: borderRadius.xl,
    alignItems: 'center',
  },
  confirmBtnText: { color: '#fff', fontSize: 17, fontWeight: fontWeights.bold },
  alertBtn: {
    paddingVertical: spacing.lg,
    borderRadius: borderRadius.xl,
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: colors.goldBorderStrong,
  },
  alertBtnText: { color: colors.goldPrimary, fontSize: 17, fontWeight: fontWeights.semibold },
});
