import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  StatusBar,
} from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import LinearGradient from 'react-native-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Polyline, Line } from 'react-native-svg';

import { colors, spacing, typography, fontWeights, borderRadius } from '../../theme';
import { journal as journalApi, analytics } from '../../services/api';
import GlassCard from '../../components/GlassCard';
import type { JournalEntry } from '../../types';
import type { JournalStackParamList } from '../../navigation/types';

type NavProp = StackNavigationProp<JournalStackParamList, 'Journal'>;
type JournalFilter = 'open' | 'closed' | 'paper';

const STATUS_CONFIG: Record<JournalEntry['status'], { label: string; color: string }> = {
  open: { label: 'OPEN', color: colors.info },
  tp1_hit: { label: 'TP1', color: colors.buyGreen },
  tp2_hit: { label: 'TP2', color: colors.buyGreen },
  tp3_hit: { label: 'TP3', color: colors.buyGreen },
  sl_hit: { label: 'SL HIT', color: colors.sellRed },
  expired: { label: 'EXPIRED', color: colors.textMuted },
  manual_close: { label: 'CLOSED', color: colors.textSecondary },
};

function MiniEquityCurve({ data }: { data: number[] }) {
  if (data.length < 2) return null;

  const width = 240;
  const height = 60;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 8) - 4;
    return `${x},${y}`;
  });

  const isPositive = data[data.length - 1] >= data[0];
  const lineColor = isPositive ? colors.buyGreen : colors.sellRed;

  return (
    <Svg width={width} height={height} style={styles.chartSvg}>
      <Polyline
        points={pts.join(' ')}
        fill="none"
        stroke={lineColor}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.85}
      />
    </Svg>
  );
}

function EntryCard({ entry, onPress }: { entry: JournalEntry; onPress: () => void }) {
  const statusConfig = STATUS_CONFIG[entry.status];
  const isBuy = entry.direction === 'BUY';
  const dirColor = isBuy ? colors.buyGreen : colors.sellRed;
  const pnlColor = (entry.pnlUsd ?? 0) >= 0 ? colors.buyGreen : colors.sellRed;
  const pnlPrefix = (entry.pnlUsd ?? 0) >= 0 ? '+' : '';

  return (
    <GlassCard onPress={onPress} padding={spacing.md} style={styles.entryCard}>
      <View style={styles.entryRow}>
        {/* Left: pair + dir */}
        <View style={styles.entryLeft}>
          <View style={[styles.dirDot, { backgroundColor: dirColor }]} />
          <View>
            <Text style={styles.pairText}>{entry.pair}</Text>
            <Text style={[styles.dirText, { color: dirColor }]}>{entry.direction}</Text>
          </View>
        </View>

        {/* Center: timeframe + status */}
        <View style={styles.entryCenter}>
          {entry.timeframe && (
            <Text style={styles.tfText}>{entry.timeframe}</Text>
          )}
          <View style={[styles.statusBadge, { borderColor: statusConfig.color }]}>
            <Text style={[styles.statusText, { color: statusConfig.color }]}>
              {statusConfig.label}
            </Text>
          </View>
          {!entry.isLive && (
            <View style={styles.paperTag}>
              <Text style={styles.paperTagText}>PAPER</Text>
            </View>
          )}
        </View>

        {/* Right: P&L + R:R */}
        <View style={styles.entryRight}>
          {entry.pnlUsd != null ? (
            <>
              <Text style={[styles.pnlText, { color: pnlColor }]}>
                {pnlPrefix}${Math.abs(entry.pnlUsd).toFixed(2)}
              </Text>
              {entry.rrAchieved != null && (
                <Text style={styles.rrText}>1:{entry.rrAchieved.toFixed(1)} R:R</Text>
              )}
            </>
          ) : (
            <Text style={styles.openText}>In Progress</Text>
          )}
        </View>
      </View>

      {/* Post-mortem hint */}
      {entry.status === 'sl_hit' && entry.postMortem && (
        <View style={styles.postMortemHint}>
          <Text style={styles.postMortemIcon}>📋</Text>
          <Text style={styles.postMortemText} numberOfLines={1}>
            {entry.postMortem.lesson}
          </Text>
        </View>
      )}
    </GlassCard>
  );
}

export default function JournalScreen() {
  const navigation = useNavigation<NavProp>();
  const insets = useSafeAreaInsets();
  const [activeTab, setActiveTab] = useState<JournalFilter>('closed');

  const { data: stats } = useQuery({
    queryKey: ['journal-stats'],
    queryFn: () => journalApi.getStats(),
    staleTime: 2 * 60_000,
  });

  const { data: entriesData, isLoading } = useQuery({
    queryKey: ['journal', activeTab],
    queryFn: () => journalApi.getJournal(1, activeTab),
    staleTime: 60_000,
  });

  const { data: equityData } = useQuery({
    queryKey: ['equity-curve'],
    queryFn: () => analytics.getEquityCurve(90),
    staleTime: 5 * 60_000,
  });

  const entries = entriesData?.items ?? [];
  const equityValues = equityData?.map((p) => p.equity) ?? [];

  const streakLabel = stats
    ? stats.currentStreak > 0
      ? `🔥 ${stats.currentStreak} win streak`
      : stats.currentStreak < 0
      ? `${Math.abs(stats.currentStreak)} loss streak`
      : 'No streak'
    : '–';

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" />
      <LinearGradient
        colors={[colors.backgroundDeep, colors.ambientGradientEnd, colors.backgroundDeep]}
        style={StyleSheet.absoluteFill}
      />

      <FlatList
        data={entries}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <EntryCard
            entry={item}
            onPress={() => navigation.navigate('JournalDetail', { entryId: item.id })}
          />
        )}
        contentContainerStyle={[
          styles.listContent,
          { paddingBottom: insets.bottom + 80 },
        ]}
        showsVerticalScrollIndicator={false}
        ListHeaderComponent={
          <>
            {/* Header */}
            <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
              <Text style={styles.title}>Trade Journal</Text>
            </View>

            {/* Stats row */}
            {stats && (
              <View style={styles.statsRow}>
                <StatCell label="Win Rate" value={`${(stats.winRate * 100).toFixed(0)}%`} positive={stats.winRate >= 0.5} />
                <StatCell label="P&L" value={`$${stats.totalPnlUsd >= 0 ? '+' : ''}${stats.totalPnlUsd.toFixed(0)}`} positive={stats.totalPnlUsd >= 0} />
                <StatCell label="Avg R:R" value={`1:${stats.avgRR.toFixed(1)}`} positive />
                <StatCell label="Streak" value={streakLabel} positive={stats.currentStreak > 0} />
              </View>
            )}

            {/* Equity curve */}
            {equityValues.length > 1 && (
              <GlassCard style={styles.equityCard} padding={spacing.md}>
                <Text style={styles.equityTitle}>90-Day Equity Curve</Text>
                <MiniEquityCurve data={equityValues} />
                {stats && (
                  <Text style={styles.maxDD}>
                    Max Drawdown: {(stats.maxDrawdownPct * 100).toFixed(1)}%
                  </Text>
                )}
              </GlassCard>
            )}

            {/* Tabs */}
            <View style={styles.tabRow}>
              {(['open', 'closed', 'paper'] as JournalFilter[]).map((tab) => (
                <TouchableOpacity
                  key={tab}
                  style={[styles.tab, activeTab === tab && styles.tabActive]}
                  onPress={() => setActiveTab(tab)}
                >
                  <Text style={[styles.tabText, activeTab === tab && styles.tabTextActive]}>
                    {tab.charAt(0).toUpperCase() + tab.slice(1)}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </>
        }
        ListEmptyComponent={
          !isLoading ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyIcon}>📒</Text>
              <Text style={styles.emptyTitle}>No {activeTab} trades</Text>
              <Text style={styles.emptySubtitle}>
                {activeTab === 'open'
                  ? 'No open positions right now.'
                  : activeTab === 'paper'
                  ? 'Enable paper trading in Settings to practice.'
                  : 'Your completed trades will appear here.'}
              </Text>
            </View>
          ) : null
        }
      />
    </View>
  );
}

function StatCell({ label, value, positive }: { label: string; value: string; positive: boolean }) {
  return (
    <GlassCard style={styles.statCell} padding={spacing.sm}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={[styles.statValue, { color: positive ? colors.buyGreen : colors.sellRed }]}>
        {value}
      </Text>
    </GlassCard>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.backgroundDeep },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  title: { ...typography.headingLarge, color: colors.textPrimary },
  statsRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  statCell: { flex: 1 },
  statLabel: { color: colors.textMuted, fontSize: 10, fontWeight: fontWeights.medium, textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 2 },
  statValue: { fontSize: 14, fontWeight: fontWeights.bold },
  equityCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
  },
  equityTitle: { color: colors.textSecondary, fontSize: 12, fontWeight: fontWeights.medium, marginBottom: spacing.sm },
  chartSvg: { alignSelf: 'center' },
  maxDD: { color: colors.textMuted, fontSize: 11, textAlign: 'right', marginTop: 4 },
  tabRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  tab: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.full,
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
  },
  tabActive: {
    backgroundColor: 'rgba(212,168,67,0.15)',
    borderColor: colors.goldBorderStrong,
  },
  tabText: { color: colors.textSecondary, fontSize: 13, fontWeight: fontWeights.medium },
  tabTextActive: { color: colors.goldPrimary, fontWeight: fontWeights.semibold },
  listContent: { paddingHorizontal: spacing.lg },
  entryCard: { marginBottom: spacing.sm },
  entryRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  entryLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, width: 80 },
  dirDot: { width: 8, height: 8, borderRadius: 4 },
  pairText: { color: colors.textPrimary, fontSize: 13, fontWeight: fontWeights.semibold },
  dirText: { fontSize: 12, fontWeight: fontWeights.bold },
  entryCenter: { flex: 1, gap: 4 },
  tfText: { color: colors.textMuted, fontSize: 11 },
  statusBadge: {
    alignSelf: 'flex-start',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    borderWidth: 1,
  },
  statusText: { fontSize: 10, fontWeight: fontWeights.bold, letterSpacing: 0.5 },
  paperTag: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(59,130,246,0.1)',
    borderRadius: 4,
    paddingHorizontal: 4,
    paddingVertical: 1,
  },
  paperTagText: { color: colors.info, fontSize: 9, fontWeight: fontWeights.bold },
  entryRight: { alignItems: 'flex-end', minWidth: 80 },
  pnlText: { fontSize: 16, fontWeight: fontWeights.bold },
  rrText: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  openText: { color: colors.textMuted, fontSize: 12, fontStyle: 'italic' },
  postMortemHint: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.glassBorder,
  },
  postMortemIcon: { fontSize: 12 },
  postMortemText: { color: colors.textMuted, fontSize: 12, flex: 1 },
  emptyState: { padding: spacing.xxxl, alignItems: 'center' },
  emptyIcon: { fontSize: 40, marginBottom: spacing.md },
  emptyTitle: { ...typography.headingSmall, color: colors.textPrimary, textAlign: 'center', marginBottom: spacing.sm },
  emptySubtitle: { color: colors.textSecondary, fontSize: 14, textAlign: 'center', lineHeight: 22 },
});
