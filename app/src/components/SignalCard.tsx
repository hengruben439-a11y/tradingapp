import React, { useRef, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Animated,
} from 'react-native';
import { BlurView } from '@react-native-community/blur';
import { colors, spacing, borderRadius, typography, fontWeights, shadows } from '../theme';
import type { Signal, SignalStrength } from '../types';
import { useUIMode } from '../store';
import ConfidenceRing from './ConfidenceRing';
import RegimeBadge from './RegimeBadge';
import ModuleDissent from './ModuleDissent';
import CountdownTimer from './CountdownTimer';
import PairFlag from './PairFlag';

interface SignalCardProps {
  signal: Signal;
  onPress?: () => void;
  onDismiss?: () => void;
}

function strengthLabel(strength: SignalStrength): string {
  switch (strength) {
    case 'very_strong': return 'Very Strong';
    case 'strong': return 'Strong';
    case 'moderate': return 'Moderate';
    case 'weak': return 'Watch';
  }
}

function formatPrice(price: number, pair: string): string {
  if (pair === 'XAUUSD') return price.toFixed(2);
  return price.toFixed(3);
}

function rrLabel(entry: number, sl: number, tp: number, direction: string): string {
  const risk = Math.abs(entry - sl);
  const reward = Math.abs(tp - entry);
  if (risk === 0) return '–';
  return `1:${(reward / risk).toFixed(1)}`;
}

export default function SignalCard({ signal, onPress, onDismiss }: SignalCardProps) {
  const { isSimpleMode, isProMode, isMaxMode } = useUIMode();
  const slideAnim = useRef(new Animated.Value(40)).current;
  const opacityAnim = useRef(new Animated.Value(0)).current;
  const [expanded, setExpanded] = useState(false);

  const isBuy = signal.direction === 'BUY';
  const accentColor = isBuy ? colors.buyGreen : colors.sellRed;
  const accentAlpha = isBuy ? colors.buyGreenAlpha : colors.sellRedAlpha;

  // Check if signal is fading
  const isFading = signal.decayedScore < 0.5 && signal.decayedScore >= 0.3;

  useEffect(() => {
    Animated.parallel([
      Animated.spring(slideAnim, {
        toValue: 0,
        tension: 80,
        friction: 12,
        useNativeDriver: true,
      }),
      Animated.timing(opacityAnim, {
        toValue: isFading ? 0.6 : 1,
        duration: 400,
        useNativeDriver: true,
      }),
    ]).start();
  }, [isFading]);

  return (
    <Animated.View
      style={[
        styles.wrapper,
        { transform: [{ translateY: slideAnim }], opacity: opacityAnim },
      ]}
    >
      <TouchableOpacity
        style={styles.container}
        onPress={onPress ?? (() => setExpanded(!expanded))}
        activeOpacity={0.9}
      >
        {/* Glass layers */}
        <BlurView
          style={StyleSheet.absoluteFill}
          blurType="dark"
          blurAmount={20}
          reducedTransparencyFallbackColor={colors.backgroundCard}
        />
        <View style={[StyleSheet.absoluteFill, styles.glassOverlay]} />

        {/* Direction accent bar */}
        <View style={[styles.accentBar, { backgroundColor: accentColor }]} />

        {/* Main content */}
        <View style={styles.content}>
          {/* Header row */}
          <View style={styles.headerRow}>
            <PairFlag pair={signal.pair} />
            <View style={styles.headerRight}>
              {signal.hasNewsRisk && (
                <View style={styles.newsBadge}>
                  <Text style={styles.newsBadgeText}>NEWS</Text>
                </View>
              )}
              {signal.hasHTFConflict && (
                <View style={styles.conflictBadge}>
                  <Text style={styles.conflictBadgeText}>CONFLICT</Text>
                </View>
              )}
              {onDismiss && (
                <TouchableOpacity style={styles.dismissBtn} onPress={onDismiss}>
                  <Text style={styles.dismissText}>✕</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>

          {/* Direction + Confidence */}
          <View style={styles.directionRow}>
            <View style={[styles.directionBadge, { backgroundColor: accentAlpha, borderColor: accentColor }]}>
              <Text style={[styles.directionText, { color: accentColor }]}>
                {signal.direction}
              </Text>
            </View>
            <View style={styles.confidenceArea}>
              {isSimpleMode ? (
                <View style={[styles.strengthBadge, { borderColor: accentColor }]}>
                  <Text style={[styles.strengthText, { color: accentColor }]}>
                    {strengthLabel(signal.strength)}
                  </Text>
                </View>
              ) : (
                <ConfidenceRing score={signal.decayedScore} size={52} />
              )}
            </View>
          </View>

          {/* Price levels */}
          <View style={styles.pricesGrid}>
            <PriceRow label="Entry" value={formatPrice(signal.entryPrice, signal.pair)} color={colors.textPrimary} />
            <PriceRow label="TP1" value={formatPrice(signal.tp1, signal.pair)} color={colors.buyGreen} />
            <PriceRow label="SL" value={formatPrice(signal.stopLoss, signal.pair)} color={colors.sellRed} />
            {!isSimpleMode && (
              <>
                <PriceRow label="TP2" value={formatPrice(signal.tp2, signal.pair)} color={colors.buyGreen} />
                <PriceRow label="TP3" value={formatPrice(signal.tp3, signal.pair)} color={colors.buyGreen} />
                <PriceRow
                  label="R:R"
                  value={rrLabel(signal.entryPrice, signal.stopLoss, signal.tp2, signal.direction)}
                  color={colors.goldPrimary}
                />
              </>
            )}
          </View>

          {/* Pro/Max footer */}
          {!isSimpleMode && (
            <View style={styles.footer}>
              <RegimeBadge regime={signal.regime} />
              {signal.killZone && (
                <View style={styles.kzBadge}>
                  <Text style={styles.kzText}>{signal.killZone}</Text>
                </View>
              )}
              {isMaxMode && (
                <CountdownTimer
                  targetTime={signal.expiresAt}
                  label="Expires"
                />
              )}
            </View>
          )}

          {isFading && (
            <View style={styles.fadingBanner}>
              <Text style={styles.fadingText}>Signal Fading</Text>
            </View>
          )}

          {/* Expanded: module dissent (Pro/Max) */}
          {expanded && !isSimpleMode && signal.dissent && signal.dissent.length > 0 && (
            <View style={styles.dissentSection}>
              <Text style={styles.dissentTitle}>Module Alignment</Text>
              <ModuleDissent modules={signal.dissent} />
            </View>
          )}
        </View>
      </TouchableOpacity>
    </Animated.View>
  );
}

function PriceRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={styles.priceRow}>
      <Text style={styles.priceLabel}>{label}</Text>
      <Text style={[styles.priceValue, { color }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
  },
  container: {
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    overflow: 'hidden',
    ...shadows.lg,
  },
  glassOverlay: {
    backgroundColor: colors.glassBackground,
  },
  accentBar: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 4,
  },
  content: {
    padding: spacing.lg,
    paddingLeft: spacing.xl,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  newsBadge: {
    backgroundColor: 'rgba(245,158,11,0.15)',
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.warning,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  newsBadgeText: {
    color: colors.warning,
    fontSize: 10,
    fontWeight: fontWeights.bold,
    letterSpacing: 0.5,
  },
  conflictBadge: {
    backgroundColor: 'rgba(239,68,68,0.15)',
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.sellRed,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  conflictBadgeText: {
    color: colors.sellRed,
    fontSize: 10,
    fontWeight: fontWeights.bold,
    letterSpacing: 0.5,
  },
  dismissBtn: {
    padding: spacing.xs,
  },
  dismissText: {
    color: colors.textMuted,
    fontSize: 14,
  },
  directionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.lg,
  },
  directionBadge: {
    borderRadius: borderRadius.md,
    borderWidth: 1.5,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
  },
  directionText: {
    fontSize: 28,
    fontWeight: fontWeights.bold,
    letterSpacing: 2,
  },
  confidenceArea: {
    alignItems: 'center',
  },
  strengthBadge: {
    borderRadius: borderRadius.md,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  strengthText: {
    fontSize: 13,
    fontWeight: fontWeights.semibold,
  },
  pricesGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  priceRow: {
    minWidth: '30%',
    flexGrow: 1,
    backgroundColor: 'rgba(255,255,255,0.03)',
    borderRadius: borderRadius.sm,
    padding: spacing.sm,
  },
  priceLabel: {
    color: colors.textSecondary,
    fontSize: 11,
    fontWeight: fontWeights.medium,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  priceValue: {
    fontSize: 15,
    fontWeight: fontWeights.semibold,
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    flexWrap: 'wrap',
  },
  kzBadge: {
    backgroundColor: 'rgba(59,130,246,0.12)',
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: 'rgba(59,130,246,0.3)',
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  kzText: {
    color: colors.info,
    fontSize: 11,
    fontWeight: fontWeights.medium,
  },
  fadingBanner: {
    marginTop: spacing.sm,
    backgroundColor: 'rgba(245,158,11,0.1)',
    borderRadius: borderRadius.sm,
    padding: spacing.xs,
    alignItems: 'center',
  },
  fadingText: {
    color: colors.warning,
    fontSize: 12,
    fontWeight: fontWeights.medium,
  },
  dissentSection: {
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.glassBorder,
  },
  dissentTitle: {
    color: colors.textSecondary,
    fontSize: 12,
    fontWeight: fontWeights.semibold,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
  },
});
