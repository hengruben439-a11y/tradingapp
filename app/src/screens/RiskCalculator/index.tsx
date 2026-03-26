import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  StatusBar,
  Alert,
} from 'react-native';
import Slider from '@react-native-community/slider';
import { useRoute, useNavigation, RouteProp } from '@react-navigation/native';
import { useQuery } from '@tanstack/react-query';
import LinearGradient from 'react-native-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing, typography, fontWeights, borderRadius } from '../../theme';
import { signals as signalsApi } from '../../services/api';
import * as storage from '../../services/storage';
import { useUIMode } from '../../store';
import GlassCard from '../../components/GlassCard';
import type { RootStackParamList } from '../../navigation/types';

type RouteType = RouteProp<RootStackParamList, 'RiskCalculator'>;

// Pip value calculation
function computePipValue(pair: string, usdJpy = 150): number {
  if (pair === 'XAUUSD') return 1.0;     // $1 per pip per std lot
  if (pair === 'GBPJPY') return (0.01 / usdJpy) * 100000; // dynamic
  return 10; // default forex majors
}

function calculateLotSize(
  balance: number,
  riskPct: number,
  slPips: number,
  pipValue: number,
): number {
  const dollarRisk = balance * (riskPct / 100);
  if (slPips <= 0 || pipValue <= 0) return 0;
  const lots = dollarRisk / (slPips * pipValue);
  return Math.max(0.01, Math.round(lots * 100) / 100);
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
}

export default function RiskCalculatorScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation();
  const insets = useSafeAreaInsets();
  const { isSimpleMode, isMaxMode } = useUIMode();

  const [balance, setBalance] = useState(String(storage.getAccountBalance()));
  const [riskPct, setRiskPct] = useState(storage.getRiskPct());
  const [selectedPair, setSelectedPair] = useState<'XAUUSD' | 'GBPJPY'>('XAUUSD');
  const [slPips, setSlPips] = useState('65');

  const signalId = route.params?.signalId;
  const { data: signal } = useQuery({
    queryKey: ['signal', signalId],
    queryFn: () => signalsApi.getSignal(signalId!),
    enabled: !!signalId,
  });

  // Pre-fill from signal
  useEffect(() => {
    if (signal) {
      setSelectedPair(signal.pair);
      setSlPips(String(signal.riskPips.toFixed(1)));
    }
  }, [signal]);

  const balanceNum = parseFloat(balance.replace(/[^0-9.]/g, '')) || 0;
  const slPipsNum = parseFloat(slPips) || 0;
  const pipValue = computePipValue(selectedPair);
  const lotSize = calculateLotSize(balanceNum, riskPct, slPipsNum, pipValue);
  const dollarRisk = balanceNum * (riskPct / 100);
  const marginRequired = lotSize * (selectedPair === 'XAUUSD' ? 2000 : 1000) * 0.03;

  const handleSaveDefaults = () => {
    storage.setAccountBalance(balanceNum);
    storage.setRiskPct(riskPct);
    Alert.alert('Saved', 'Default risk settings updated.');
  };

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" />
      <LinearGradient
        colors={[colors.backgroundDeep, colors.ambientGradientEnd, colors.backgroundDeep]}
        style={StyleSheet.absoluteFill}
      />

      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.closeBtn}>
          <Text style={styles.closeBtnText}>✕</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Risk Calculator</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 40 }]}
        showsVerticalScrollIndicator={false}
      >
        {/* Balance input */}
        <GlassCard style={styles.card} padding={spacing.lg}>
          <Text style={styles.label}>Account Balance (USD)</Text>
          <View style={styles.inputRow}>
            <Text style={styles.currencyPrefix}>$</Text>
            <TextInput
              style={styles.balanceInput}
              value={balance}
              onChangeText={setBalance}
              keyboardType="numeric"
              placeholder="10,000"
              placeholderTextColor={colors.textMuted}
              returnKeyType="done"
            />
          </View>
        </GlassCard>

        {/* Risk slider */}
        <GlassCard style={styles.card} padding={spacing.lg}>
          <View style={styles.sliderHeader}>
            <Text style={styles.label}>Risk Per Trade</Text>
            <Text style={styles.sliderValue}>{riskPct.toFixed(1)}%</Text>
          </View>
          {isSimpleMode ? (
            <View style={styles.simpleRiskRow}>
              {[0.5, 1, 1.5, 2].map((v) => (
                <TouchableOpacity
                  key={v}
                  style={[styles.riskBtn, riskPct === v && styles.riskBtnActive]}
                  onPress={() => setRiskPct(v)}
                >
                  <Text style={[styles.riskBtnText, riskPct === v && styles.riskBtnTextActive]}>
                    {v}%
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          ) : (
            <Slider
              value={riskPct}
              onValueChange={setRiskPct}
              minimumValue={isMaxMode ? 0.1 : 0.5}
              maximumValue={isMaxMode ? 5 : 5}
              step={isMaxMode ? 0.1 : 0.5}
              minimumTrackTintColor={colors.goldPrimary}
              maximumTrackTintColor={colors.glassBorder}
              thumbTintColor={colors.goldPrimary}
            />
          )}
          <Text style={styles.dollarRiskLabel}>
            Dollar Risk: <Text style={styles.dollarRiskValue}>{formatCurrency(dollarRisk)}</Text>
          </Text>
        </GlassCard>

        {/* Pair selector */}
        <GlassCard style={styles.card} padding={spacing.lg}>
          <Text style={styles.label}>Trading Pair</Text>
          <View style={styles.pairRow}>
            {(['XAUUSD', 'GBPJPY'] as const).map((p) => (
              <TouchableOpacity
                key={p}
                style={[styles.pairBtn, selectedPair === p && styles.pairBtnActive]}
                onPress={() => setSelectedPair(p)}
              >
                <Text style={styles.pairBtnEmoji}>{p === 'XAUUSD' ? '🥇' : '🇬🇧🇯🇵'}</Text>
                <Text style={[styles.pairBtnText, selectedPair === p && styles.pairBtnTextActive]}>
                  {p}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </GlassCard>

        {/* SL Distance */}
        <GlassCard style={styles.card} padding={spacing.lg}>
          <Text style={styles.label}>Stop Loss Distance (pips)</Text>
          <TextInput
            style={styles.slInput}
            value={slPips}
            onChangeText={setSlPips}
            keyboardType="numeric"
            placeholder="65"
            placeholderTextColor={colors.textMuted}
            returnKeyType="done"
          />
          {signal && (
            <Text style={styles.autoFillNote}>Auto-filled from signal #{signal.id.slice(0, 8)}</Text>
          )}
        </GlassCard>

        {/* Results */}
        <GlassCard style={styles.resultsCard} padding={spacing.lg} borderHighlight>
          <Text style={styles.resultsTitle}>Position Size</Text>
          <Text style={styles.lotSizeText}>{lotSize.toFixed(2)} lots</Text>
          <Text style={styles.lotSubtext}>Standard lots (100,000 units)</Text>

          <View style={styles.resultsDivider} />

          <View style={styles.resultsGrid}>
            <ResultItem label="Dollar Risk" value={formatCurrency(dollarRisk)} color={colors.sellRed} />
            <ResultItem label="Pip Value" value={`$${pipValue.toFixed(2)}/pip`} />
            {!isSimpleMode && (
              <ResultItem label="Margin Est." value={formatCurrency(marginRequired)} color={colors.warning} />
            )}
          </View>

          <View style={styles.riskSummary}>
            <Text style={styles.riskSummaryText}>
              Risking {riskPct}% of {formatCurrency(balanceNum)} ={' '}
              <Text style={{ color: colors.goldPrimary, fontWeight: fontWeights.bold }}>
                {formatCurrency(dollarRisk)}
              </Text>{' '}
              → <Text style={{ color: colors.textPrimary }}>{lotSize.toFixed(2)} lots</Text> on{' '}
              {selectedPair} with {slPipsNum.toFixed(1)}-pip SL
            </Text>
          </View>
        </GlassCard>

        {/* Correlation warning */}
        <View style={styles.correlationNote}>
          <Text style={styles.correlationNoteText}>
            ⚠️  Trading both XAUUSD and GBPJPY simultaneously can create conflicting macro exposure. Always check signal correlation warnings.
          </Text>
        </View>

        {/* Save defaults */}
        <TouchableOpacity style={styles.saveBtn} onPress={handleSaveDefaults}>
          <Text style={styles.saveBtnText}>Save as Default</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

function ResultItem({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.resultItem}>
      <Text style={styles.resultItemLabel}>{label}</Text>
      <Text style={[styles.resultItemValue, color ? { color } : {}]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.backgroundDeep },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  closeBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  closeBtnText: { color: colors.textSecondary, fontSize: 18 },
  title: { ...typography.headingMedium, color: colors.textPrimary },
  content: { paddingHorizontal: spacing.lg, gap: spacing.md },
  card: { marginBottom: 0 },
  label: {
    color: colors.textSecondary,
    fontSize: 12,
    fontWeight: fontWeights.semibold,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
  },
  inputRow: { flexDirection: 'row', alignItems: 'center' },
  currencyPrefix: { color: colors.textSecondary, fontSize: 22, fontWeight: fontWeights.medium, marginRight: spacing.sm },
  balanceInput: {
    flex: 1,
    color: colors.textPrimary,
    fontSize: 28,
    fontWeight: fontWeights.bold,
  },
  sliderHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sliderValue: { color: colors.goldPrimary, fontSize: 20, fontWeight: fontWeights.bold },
  simpleRiskRow: { flexDirection: 'row', gap: spacing.sm },
  riskBtn: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md,
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
  },
  riskBtnActive: { backgroundColor: 'rgba(212,168,67,0.15)', borderColor: colors.goldBorderStrong },
  riskBtnText: { color: colors.textSecondary, fontSize: 14, fontWeight: fontWeights.medium },
  riskBtnTextActive: { color: colors.goldPrimary, fontWeight: fontWeights.bold },
  dollarRiskLabel: { color: colors.textMuted, fontSize: 13, marginTop: spacing.sm },
  dollarRiskValue: { color: colors.sellRed, fontWeight: fontWeights.semibold },
  pairRow: { flexDirection: 'row', gap: spacing.sm },
  pairBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.md,
    borderRadius: borderRadius.lg,
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
  },
  pairBtnActive: { backgroundColor: 'rgba(212,168,67,0.15)', borderColor: colors.goldBorderStrong },
  pairBtnEmoji: { fontSize: 18 },
  pairBtnText: { color: colors.textSecondary, fontSize: 14, fontWeight: fontWeights.semibold },
  pairBtnTextActive: { color: colors.goldPrimary },
  slInput: {
    color: colors.textPrimary,
    fontSize: 24,
    fontWeight: fontWeights.bold,
    borderBottomWidth: 1,
    borderBottomColor: colors.goldBorder,
    paddingBottom: spacing.xs,
  },
  autoFillNote: { color: colors.textMuted, fontSize: 11, marginTop: spacing.xs },
  resultsCard: { marginBottom: 0 },
  resultsTitle: { color: colors.textSecondary, fontSize: 12, fontWeight: fontWeights.semibold, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: spacing.sm },
  lotSizeText: { color: colors.goldPrimary, fontSize: 48, fontWeight: fontWeights.bold, lineHeight: 56 },
  lotSubtext: { color: colors.textMuted, fontSize: 12, marginBottom: spacing.md },
  resultsDivider: { height: 1, backgroundColor: colors.glassBorder, marginVertical: spacing.md },
  resultsGrid: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md },
  resultItem: { flex: 1, alignItems: 'center' },
  resultItemLabel: { color: colors.textMuted, fontSize: 10, fontWeight: fontWeights.medium, textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 3 },
  resultItemValue: { color: colors.textPrimary, fontSize: 14, fontWeight: fontWeights.bold },
  riskSummary: {
    backgroundColor: 'rgba(255,255,255,0.03)',
    borderRadius: borderRadius.md,
    padding: spacing.md,
  },
  riskSummaryText: { color: colors.textSecondary, fontSize: 13, lineHeight: 20 },
  correlationNote: {
    backgroundColor: 'rgba(245,158,11,0.06)',
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: 'rgba(245,158,11,0.2)',
    padding: spacing.md,
  },
  correlationNoteText: { color: colors.warning, fontSize: 12, lineHeight: 18 },
  saveBtn: {
    paddingVertical: spacing.lg,
    borderRadius: borderRadius.xl,
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: colors.goldBorderStrong,
  },
  saveBtnText: { color: colors.goldPrimary, fontSize: 16, fontWeight: fontWeights.semibold },
});
