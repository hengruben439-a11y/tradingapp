import React, { useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Animated,
  RefreshControl,
  StatusBar,
  Platform,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import LinearGradient from 'react-native-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { StackNavigationProp } from '@react-navigation/stack';

import { colors, spacing, typography, fontWeights, borderRadius } from '../../theme';
import { signals as signalsApi } from '../../services/api';
import { useUIMode, useSignals, useStore, useNotifications } from '../../store';
import { useWebSocket } from '../../services/websocket';
import SignalCard from '../../components/SignalCard';
import type { Signal, TradingStyle } from '../../types';
import type { HomeStackParamList } from '../../navigation/types';

type NavProp = StackNavigationProp<HomeStackParamList, 'Dashboard'>;

const STYLE_OPTIONS: { label: string; value: TradingStyle }[] = [
  { label: 'Scalp', value: 'scalping' },
  { label: 'Day', value: 'day_trading' },
  { label: 'Swing', value: 'swing_trading' },
  { label: 'Position', value: 'position_trading' },
];

function EmptyState() {
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.1, duration: 1200, useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 1, duration: 1200, useNativeDriver: true }),
      ]),
    ).start();
  }, [pulseAnim]);

  return (
    <View style={emptyStyles.container}>
      <Animated.View style={[emptyStyles.orb, { transform: [{ scale: pulseAnim }] }]} />
      <Text style={emptyStyles.title}>Market is Quiet</Text>
      <Text style={emptyStyles.subtitle}>
        No signals right now. The engine is watching for high-confidence setups.
      </Text>
    </View>
  );
}

const emptyStyles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xxxl,
    marginTop: 60,
  },
  orb: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: 'rgba(212,168,67,0.12)',
    borderWidth: 1.5,
    borderColor: colors.goldBorder,
    marginBottom: spacing.xxl,
  },
  title: {
    ...typography.headingMedium,
    color: colors.textPrimary,
    textAlign: 'center',
    marginBottom: spacing.sm,
  },
  subtitle: {
    ...typography.bodyMedium,
    color: colors.textSecondary,
    textAlign: 'center',
    lineHeight: 22,
  },
});

export default function DashboardScreen() {
  const navigation = useNavigation<NavProp>();
  const insets = useSafeAreaInsets();
  const queryClient = useQueryClient();
  const { isSimpleMode, tradingStyle, setTradingStyle } = useUIMode();
  const { setActiveSignals, activeSignals, dismissSignal } = useSignals();
  const { unreadCount, markAllRead } = useNotifications();
  const { lastSignal, connected } = useWebSocket();

  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['signals', tradingStyle],
    queryFn: () => signalsApi.getActiveSignals(tradingStyle),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  useEffect(() => {
    if (data) {
      let displayData = isSimpleMode ? data.slice(0, 2) : data;
      setActiveSignals(displayData);
    }
  }, [data, isSimpleMode, setActiveSignals]);

  // Live signal injection from WebSocket
  useEffect(() => {
    if (lastSignal) {
      useStore.getState().addOrUpdateSignal(lastSignal);
      useStore.getState().incrementUnread();
    }
  }, [lastSignal]);

  const handleSignalPress = useCallback(
    (signal: Signal) => {
      navigation.navigate('SignalDetail', { signalId: signal.id });
    },
    [navigation],
  );

  const renderSignal = useCallback(
    ({ item }: { item: Signal }) => (
      <SignalCard
        signal={item}
        onPress={() => handleSignalPress(item)}
        onDismiss={() => dismissSignal(item.id)}
      />
    ),
    [handleSignalPress, dismissSignal],
  );

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" />

      {/* Ambient background */}
      <LinearGradient
        colors={[colors.backgroundDeep, colors.ambientGradientEnd, colors.backgroundDeep]}
        locations={[0, 0.5, 1]}
        style={StyleSheet.absoluteFill}
      />
      {/* Purple orbs */}
      <View style={[styles.orb, styles.orb1]} />
      <View style={[styles.orb, styles.orb2]} />

      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <View>
          <Text style={styles.logo}>made.</Text>
          <View style={styles.connectionRow}>
            <View style={[styles.dot, { backgroundColor: connected ? colors.buyGreen : colors.sellRed }]} />
            <Text style={styles.connectionText}>{connected ? 'Live' : 'Reconnecting...'}</Text>
          </View>
        </View>
        <TouchableOpacity style={styles.bellBtn} onPress={markAllRead}>
          <Text style={styles.bellIcon}>🔔</Text>
          {unreadCount > 0 && (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{unreadCount > 9 ? '9+' : unreadCount}</Text>
            </View>
          )}
        </TouchableOpacity>
      </View>

      {/* Trading style selector */}
      <View style={styles.styleSelector}>
        {STYLE_OPTIONS.map((opt) => (
          <TouchableOpacity
            key={opt.value}
            style={[
              styles.stylePill,
              tradingStyle === opt.value && styles.stylePillActive,
            ]}
            onPress={() => setTradingStyle(opt.value)}
          >
            <Text
              style={[
                styles.stylePillText,
                tradingStyle === opt.value && styles.stylePillTextActive,
              ]}
            >
              {opt.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Signals count */}
      {activeSignals.length > 0 && (
        <View style={styles.countRow}>
          <Text style={styles.countText}>
            {activeSignals.length} active signal{activeSignals.length !== 1 ? 's' : ''}
          </Text>
          {isSimpleMode && (
            <Text style={styles.simpleModeNote}>Showing top {Math.min(2, activeSignals.length)} (Simple Mode)</Text>
          )}
        </View>
      )}

      {/* Signal list */}
      <FlatList
        data={activeSignals}
        keyExtractor={(item) => item.id}
        renderItem={renderSignal}
        contentContainerStyle={[
          styles.listContent,
          { paddingBottom: insets.bottom + 80 },
        ]}
        ListEmptyComponent={isLoading ? null : <EmptyState />}
        refreshControl={
          <RefreshControl
            refreshing={isRefetching}
            onRefresh={refetch}
            tintColor={colors.goldPrimary}
            colors={[colors.goldPrimary]}
          />
        }
        showsVerticalScrollIndicator={false}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.backgroundDeep,
  },
  orb: {
    position: 'absolute',
    borderRadius: 999,
    opacity: 0.4,
  },
  orb1: {
    width: 280,
    height: 280,
    backgroundColor: colors.ambientGradientStart,
    top: -80,
    right: -80,
  },
  orb2: {
    width: 200,
    height: 200,
    backgroundColor: '#1A0A3E',
    bottom: 100,
    left: -60,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  logo: {
    fontSize: 28,
    fontWeight: fontWeights.bold,
    color: colors.goldPrimary,
    letterSpacing: -0.5,
  },
  connectionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginTop: 2,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  connectionText: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: fontWeights.medium,
  },
  bellBtn: {
    position: 'relative',
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bellIcon: {
    fontSize: 20,
  },
  badge: {
    position: 'absolute',
    top: 4,
    right: 4,
    backgroundColor: colors.sellRed,
    borderRadius: 8,
    minWidth: 16,
    height: 16,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 3,
  },
  badgeText: {
    color: '#fff',
    fontSize: 9,
    fontWeight: fontWeights.bold,
  },
  styleSelector: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  stylePill: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.full,
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
  },
  stylePillActive: {
    backgroundColor: 'rgba(212,168,67,0.15)',
    borderColor: colors.goldBorderStrong,
  },
  stylePillText: {
    color: colors.textSecondary,
    fontSize: 12,
    fontWeight: fontWeights.medium,
  },
  stylePillTextActive: {
    color: colors.goldPrimary,
    fontWeight: fontWeights.semibold,
  },
  countRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  countText: {
    color: colors.textSecondary,
    fontSize: 13,
    fontWeight: fontWeights.medium,
  },
  simpleModeNote: {
    color: colors.textMuted,
    fontSize: 11,
  },
  listContent: {
    paddingTop: spacing.xs,
  },
});
