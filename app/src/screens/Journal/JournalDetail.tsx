import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  StatusBar,
} from 'react-native';
import { useRoute, useNavigation, RouteProp } from '@react-navigation/native';
import { useQuery } from '@tanstack/react-query';
import LinearGradient from 'react-native-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing, typography, fontWeights, borderRadius } from '../../theme';
import { journal as journalApi } from '../../services/api';
import GlassCard from '../../components/GlassCard';
import type { JournalStackParamList } from '../../navigation/types';

type RouteType = RouteProp<JournalStackParamList, 'JournalDetail'>;

export default function JournalDetailScreen() {
  const route = useRoute<RouteType>();
  const navigation = useNavigation();
  const insets = useSafeAreaInsets();

  // Fetch entry from cache or API — in production you'd have a getEntry(id) call
  const { data: allEntries } = useQuery({
    queryKey: ['journal', 'closed'],
    queryFn: () => journalApi.getJournal(1, 'closed'),
    staleTime: 60_000,
  });

  const entry = allEntries?.items.find((e) => e.id === route.params.entryId);

  if (!entry) {
    return (
      <View style={styles.loading}>
        <Text style={styles.loadingText}>Loading entry...</Text>
      </View>
    );
  }

  const isBuy = entry.direction === 'BUY';
  const dirColor = isBuy ? colors.buyGreen : colors.sellRed;
  const pnlColor = (entry.pnlUsd ?? 0) >= 0 ? colors.buyGreen : colors.sellRed;

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" />
      <LinearGradient
        colors={[colors.backgroundDeep, colors.ambientGradientEnd, colors.backgroundDeep]}
        style={StyleSheet.absoluteFill}
      />

      <TouchableOpacity
        style={[styles.backBtn, { top: insets.top + 8 }]}
        onPress={() => navigation.goBack()}
      >
        <Text style={styles.backText}>← Journal</Text>
      </TouchableOpacity>

      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + 60, paddingBottom: insets.bottom + 40 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <GlassCard style={styles.card} borderHighlight>
          <View style={styles.headerRow}>
            <View>
              <Text style={styles.pairText}>{entry.pair}</Text>
              {entry.timeframe && <Text style={styles.tfText}>{entry.timeframe}</Text>}
            </View>
            <Text style={[styles.dirText, { color: dirColor }]}>{entry.direction}</Text>
          </View>

          {entry.pnlUsd != null && (
            <Text style={[styles.pnlBig, { color: pnlColor }]}>
              {entry.pnlUsd >= 0 ? '+' : ''}${Math.abs(entry.pnlUsd).toFixed(2)}
              {entry.pnlPips != null && (
                <Text style={styles.pipsText}> ({entry.pnlPips >= 0 ? '+' : ''}{entry.pnlPips.toFixed(1)} pips)</Text>
              )}
            </Text>
          )}

          {!entry.isLive && (
            <View style={styles.paperBadge}>
              <Text style={styles.paperBadgeText}>PAPER TRADE</Text>
            </View>
          )}
        </GlassCard>

        {/* Trade details */}
        <GlassCard style={styles.card} padding={spacing.md}>
          <Text style={styles.sectionTitle}>Trade Details</Text>
          <View style={styles.detailsGrid}>
            <DetailRow label="Entry" value={entry.entryPrice.toFixed(2)} />
            <DetailRow label="Exit" value={entry.exitPrice?.toFixed(2) ?? '–'} />
            <DetailRow label="Stop Loss" value={entry.stopLoss.toFixed(2)} color={colors.sellRed} />
            <DetailRow label="TP1" value={entry.tp1.toFixed(2)} color={colors.buyGreen} />
            <DetailRow label="TP2" value={entry.tp2.toFixed(2)} color={colors.buyGreen} />
            <DetailRow label="TP3" value={entry.tp3.toFixed(2)} color={colors.buyGreen} />
            <DetailRow label="Lot Size" value={`${entry.lotSize.toFixed(2)} lots`} />
            {entry.rrAchieved != null && (
              <DetailRow label="R:R Achieved" value={`1:${entry.rrAchieved.toFixed(1)}`} color={colors.goldPrimary} />
            )}
          </View>
        </GlassCard>

        {/* Timing */}
        <GlassCard style={styles.card} padding={spacing.md}>
          <Text style={styles.sectionTitle}>Timing</Text>
          <DetailRow label="Entry Time" value={new Date(entry.entryTime).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })} />
          {entry.exitTime && (
            <DetailRow label="Exit Time" value={new Date(entry.exitTime).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })} />
          )}
          {entry.newsFlag && (
            <View style={styles.newsFlagBadge}>
              <Text style={styles.newsFlagText}>⚡ High-impact news was active during this trade</Text>
            </View>
          )}
        </GlassCard>

        {/* Post-mortem */}
        {entry.postMortem && (
          <GlassCard style={styles.card} padding={spacing.md}>
            <Text style={styles.sectionTitle}>Signal Post-Mortem</Text>

            <View style={styles.pmSection}>
              <Text style={styles.pmLabel}>Failed Module</Text>
              <Text style={styles.pmContent}>{entry.postMortem.failedModule.replace(/_/g, ' ')}</Text>
            </View>

            <View style={styles.pmSection}>
              <Text style={styles.pmLabel}>What Happened</Text>
              <Text style={styles.pmContent}>{entry.postMortem.whatHappened}</Text>
            </View>

            <View style={[styles.pmSection, styles.lessonSection]}>
              <Text style={styles.lessonLabel}>Lesson</Text>
              <Text style={styles.lessonContent}>{entry.postMortem.lesson}</Text>
            </View>
          </GlassCard>
        )}

        {/* Notes */}
        {entry.notes && (
          <GlassCard style={styles.card} padding={spacing.md}>
            <Text style={styles.sectionTitle}>Notes</Text>
            <Text style={styles.notesText}>{entry.notes}</Text>
          </GlassCard>
        )}
      </ScrollView>
    </View>
  );
}

function DetailRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.detailRow}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={[styles.detailValue, color ? { color } : {}]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.backgroundDeep },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.backgroundDeep },
  loadingText: { color: colors.textSecondary },
  backBtn: { position: 'absolute', left: spacing.lg, zIndex: 10, padding: spacing.sm },
  backText: { color: colors.goldPrimary, fontSize: 16, fontWeight: fontWeights.medium },
  content: { paddingHorizontal: spacing.lg, gap: spacing.md },
  card: { marginBottom: 0 },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: spacing.md },
  pairText: { ...typography.headingLarge, color: colors.textPrimary },
  tfText: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  dirText: { fontSize: 28, fontWeight: fontWeights.bold, letterSpacing: 2 },
  pnlBig: { fontSize: 32, fontWeight: fontWeights.bold, marginBottom: spacing.sm },
  pipsText: { fontSize: 16, fontWeight: fontWeights.regular },
  paperBadge: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(59,130,246,0.1)',
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: 'rgba(59,130,246,0.3)',
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    marginTop: spacing.xs,
  },
  paperBadgeText: { color: colors.info, fontSize: 10, fontWeight: fontWeights.bold, letterSpacing: 0.5 },
  sectionTitle: { ...typography.headingSmall, color: colors.textPrimary, marginBottom: spacing.md },
  detailsGrid: { gap: spacing.xs },
  detailRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: spacing.xs, borderBottomWidth: 1, borderBottomColor: colors.glassBorder },
  detailLabel: { color: colors.textSecondary, fontSize: 13 },
  detailValue: { color: colors.textPrimary, fontSize: 13, fontWeight: fontWeights.medium },
  newsFlagBadge: {
    marginTop: spacing.sm,
    backgroundColor: 'rgba(245,158,11,0.1)',
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: 'rgba(245,158,11,0.25)',
    padding: spacing.sm,
  },
  newsFlagText: { color: colors.warning, fontSize: 12 },
  pmSection: { marginBottom: spacing.md },
  pmLabel: { color: colors.textMuted, fontSize: 11, fontWeight: fontWeights.semibold, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: spacing.xs },
  pmContent: { color: colors.textSecondary, fontSize: 14, lineHeight: 22 },
  lessonSection: {
    backgroundColor: 'rgba(212,168,67,0.06)',
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.goldBorder,
    padding: spacing.md,
    marginBottom: 0,
  },
  lessonLabel: { color: colors.goldPrimary, fontSize: 11, fontWeight: fontWeights.bold, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: spacing.xs },
  lessonContent: { color: colors.textPrimary, fontSize: 14, lineHeight: 22 },
  notesText: { color: colors.textSecondary, fontSize: 14, lineHeight: 22 },
});
