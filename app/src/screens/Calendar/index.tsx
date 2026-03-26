import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Animated,
  StatusBar,
} from 'react-native';
import { useQuery } from '@tanstack/react-query';
import LinearGradient from 'react-native-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing, typography, fontWeights, borderRadius } from '../../theme';
import { calendar as calendarApi } from '../../services/api';
import { useUIMode } from '../../store';
import CountdownTimer from '../../components/CountdownTimer';
import GlassCard from '../../components/GlassCard';
import type { CalendarEvent } from '../../types';

type ImpactFilter = 'all' | 'high' | 'medium' | 'low';

const IMPACT_CONFIG = {
  high: { label: 'HIGH', color: colors.sellRed, bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.3)' },
  medium: { label: 'MED', color: colors.warning, bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.3)' },
  low: { label: 'LOW', color: colors.textMuted, bg: 'rgba(107,114,128,0.1)', border: 'rgba(107,114,128,0.2)' },
};

function formatEventTime(isoDate: string, timezone: string): string {
  try {
    return new Date(isoDate).toLocaleTimeString('en-SG', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: timezone,
      hour12: false,
    });
  } catch {
    return '--:--';
  }
}

function formatEventDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString('en-SG', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

function isWithin15Min(isoDate: string): boolean {
  const diff = new Date(isoDate).getTime() - Date.now();
  return diff > 0 && diff <= 15 * 60 * 1000;
}

function EventCard({ event, timezone }: { event: CalendarEvent; timezone: string }) {
  const impactStyle = IMPACT_CONFIG[event.impact];
  const [expanded, setExpanded] = useState(false);
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const isNear = isWithin15Min(event.datetime);
  const isPast = new Date(event.datetime).getTime() < Date.now();

  useEffect(() => {
    if (event.impact === 'high' && !isPast) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.05, duration: 1000, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1, duration: 1000, useNativeDriver: true }),
        ]),
      ).start();
    }
  }, [event.impact, isPast, pulseAnim]);

  return (
    <Animated.View style={event.impact === 'high' && !isPast ? { transform: [{ scale: pulseAnim }] } : undefined}>
      <GlassCard
        onPress={() => setExpanded(!expanded)}
        style={[
          styles.eventCard,
          isPast && styles.eventCardPast,
          event.impact === 'high' && !isPast && styles.eventCardHighGlow,
        ]}
        padding={spacing.md}
      >
        <View style={styles.eventRow}>
          {/* Time */}
          <View style={styles.timeCol}>
            <Text style={[styles.timeText, isPast && styles.pastText]}>
              {formatEventTime(event.datetime, timezone)}
            </Text>
            {!isPast && (
              <CountdownTimer targetTime={event.datetime} />
            )}
          </View>

          {/* Content */}
          <View style={styles.eventContent}>
            <View style={styles.eventHeader}>
              <Text style={styles.currencyText}>{event.currency}</Text>
              <Text style={[styles.titleText, isPast && styles.pastText]}>
                {event.title}
              </Text>
            </View>

            <View style={styles.eventFooter}>
              <View style={[styles.impactBadge, { backgroundColor: impactStyle.bg, borderColor: impactStyle.border }]}>
                <Text style={[styles.impactText, { color: impactStyle.color }]}>{impactStyle.label}</Text>
              </View>

              {event.pairsAffected.length > 0 && (
                <View style={styles.pairsRow}>
                  {event.pairsAffected.map((p) => (
                    <View key={p} style={styles.pairTag}>
                      <Text style={styles.pairTagText}>{p}</Text>
                    </View>
                  ))}
                </View>
              )}

              {isNear && (
                <View style={styles.suppressBadge}>
                  <Text style={styles.suppressText}>SIGNALS SUPPRESSED</Text>
                </View>
              )}
            </View>
          </View>
        </View>

        {/* Expanded data */}
        {expanded && (
          <View style={styles.expandedData}>
            <DataRow label="Forecast" value={event.forecast ?? '–'} />
            <DataRow label="Previous" value={event.previous ?? '–'} />
            {event.actual && <DataRow label="Actual" value={event.actual} highlight />}
          </View>
        )}
      </GlassCard>
    </Animated.View>
  );
}

function DataRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <View style={styles.dataRow}>
      <Text style={styles.dataLabel}>{label}</Text>
      <Text style={[styles.dataValue, highlight && { color: colors.goldPrimary }]}>{value}</Text>
    </View>
  );
}

export default function CalendarScreen() {
  const insets = useSafeAreaInsets();
  const { isSimpleMode } = useUIMode();
  const [filter, setFilter] = useState<ImpactFilter>(isSimpleMode ? 'high' : 'all');
  const timezone = 'Asia/Singapore';

  const { data: events = [], isLoading, refetch } = useQuery({
    queryKey: ['calendar', 'upcoming'],
    queryFn: () => calendarApi.getUpcoming(7),
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
  });

  const filteredEvents = events.filter((e) => {
    if (filter === 'all') return true;
    return e.impact === filter;
  });

  // Group by date
  const grouped = filteredEvents.reduce<Record<string, CalendarEvent[]>>((acc, event) => {
    const date = formatEventDate(event.datetime);
    if (!acc[date]) acc[date] = [];
    acc[date].push(event);
    return acc;
  }, {});

  const sections = Object.entries(grouped).map(([date, items]) => ({ date, items }));

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" />
      <LinearGradient
        colors={[colors.backgroundDeep, colors.ambientGradientEnd, colors.backgroundDeep]}
        style={StyleSheet.absoluteFill}
      />

      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.title}>Economic Calendar</Text>
        <Text style={styles.subtitle}>SGT (UTC+8) · Next 7 days</Text>
      </View>

      {/* Filter tabs */}
      {!isSimpleMode && (
        <View style={styles.filterRow}>
          {(['all', 'high', 'medium', 'low'] as ImpactFilter[]).map((f) => (
            <TouchableOpacity
              key={f}
              style={[styles.filterTab, filter === f && styles.filterTabActive]}
              onPress={() => setFilter(f)}
            >
              <Text style={[styles.filterTabText, filter === f && styles.filterTabTextActive]}>
                {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {isSimpleMode && (
        <View style={styles.simpleModeNote}>
          <Text style={styles.simpleModeNoteText}>Showing high-impact events only</Text>
        </View>
      )}

      <FlatList
        data={sections}
        keyExtractor={(item) => item.date}
        renderItem={({ item }) => (
          <View>
            <View style={styles.dateHeader}>
              <Text style={styles.dateHeaderText}>{item.date}</Text>
            </View>
            {item.items.map((event) => (
              <EventCard key={event.id} event={event} timezone={timezone} />
            ))}
          </View>
        )}
        contentContainerStyle={[
          styles.listContent,
          { paddingBottom: insets.bottom + 80 },
        ]}
        ListEmptyComponent={
          !isLoading ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyText}>No events scheduled</Text>
            </View>
          ) : null
        }
        showsVerticalScrollIndicator={false}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.backgroundDeep },
  header: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  title: { ...typography.headingLarge, color: colors.textPrimary },
  subtitle: { color: colors.textSecondary, fontSize: 13, marginTop: 2 },
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  filterTab: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.full,
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
  },
  filterTabActive: {
    backgroundColor: 'rgba(212,168,67,0.15)',
    borderColor: colors.goldBorderStrong,
  },
  filterTabText: { color: colors.textSecondary, fontSize: 12, fontWeight: fontWeights.medium },
  filterTabTextActive: { color: colors.goldPrimary, fontWeight: fontWeights.semibold },
  simpleModeNote: {
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  simpleModeNoteText: { color: colors.textMuted, fontSize: 12 },
  listContent: { paddingHorizontal: spacing.lg },
  dateHeader: {
    paddingVertical: spacing.sm,
    marginTop: spacing.md,
  },
  dateHeaderText: {
    color: colors.goldPrimary,
    fontSize: 13,
    fontWeight: fontWeights.semibold,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  eventCard: { marginBottom: spacing.sm },
  eventCardPast: { opacity: 0.5 },
  eventCardHighGlow: {
    borderColor: 'rgba(239,68,68,0.3)',
    shadowColor: 'rgba(239,68,68,0.2)',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 1,
    shadowRadius: 12,
  },
  eventRow: { flexDirection: 'row', gap: spacing.md },
  timeCol: { width: 60, alignItems: 'flex-start' },
  timeText: { color: colors.textPrimary, fontSize: 14, fontWeight: fontWeights.semibold },
  pastText: { color: colors.textMuted },
  eventContent: { flex: 1 },
  eventHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.xs },
  currencyText: {
    color: colors.goldPrimary,
    fontSize: 12,
    fontWeight: fontWeights.bold,
    minWidth: 28,
  },
  titleText: { color: colors.textPrimary, fontSize: 14, fontWeight: fontWeights.medium, flex: 1 },
  eventFooter: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, alignItems: 'center' },
  impactBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    borderWidth: 1,
  },
  impactText: { fontSize: 10, fontWeight: fontWeights.bold, letterSpacing: 0.5 },
  pairsRow: { flexDirection: 'row', gap: 4 },
  pairTag: {
    backgroundColor: 'rgba(59,130,246,0.1)',
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  pairTagText: { color: colors.info, fontSize: 10, fontWeight: fontWeights.medium },
  suppressBadge: {
    backgroundColor: 'rgba(245,158,11,0.12)',
    borderRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(245,158,11,0.3)',
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  suppressText: { color: colors.warning, fontSize: 9, fontWeight: fontWeights.bold, letterSpacing: 0.4 },
  expandedData: {
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.glassBorder,
    gap: spacing.xs,
  },
  dataRow: { flexDirection: 'row', justifyContent: 'space-between' },
  dataLabel: { color: colors.textMuted, fontSize: 12 },
  dataValue: { color: colors.textPrimary, fontSize: 12, fontWeight: fontWeights.medium },
  emptyState: { padding: spacing.xxxl, alignItems: 'center' },
  emptyText: { color: colors.textSecondary },
});
