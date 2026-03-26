import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, fontWeights } from '../theme';
import type { MarketRegime } from '../types';

interface RegimeBadgeProps {
  regime: MarketRegime;
}

interface RegimeStyle {
  label: string;
  color: string;
  bg: string;
  border: string;
}

const REGIME_STYLES: Record<MarketRegime, RegimeStyle> = {
  trending: {
    label: 'TRENDING',
    color: colors.buyGreen,
    bg: colors.buyGreenAlpha,
    border: 'rgba(34,197,94,0.3)',
  },
  ranging: {
    label: 'RANGING',
    color: colors.warning,
    bg: 'rgba(245,158,11,0.12)',
    border: 'rgba(245,158,11,0.3)',
  },
  transitional: {
    label: 'TRANSITIONAL',
    color: colors.info,
    bg: 'rgba(59,130,246,0.12)',
    border: 'rgba(59,130,246,0.3)',
  },
  unknown: {
    label: 'UNKNOWN',
    color: colors.textMuted,
    bg: 'rgba(107,114,128,0.12)',
    border: 'rgba(107,114,128,0.3)',
  },
};

export default function RegimeBadge({ regime }: RegimeBadgeProps) {
  const style = REGIME_STYLES[regime];

  return (
    <View
      style={[
        styles.badge,
        {
          backgroundColor: style.bg,
          borderColor: style.border,
        },
      ]}
    >
      <View style={[styles.dot, { backgroundColor: style.color }]} />
      <Text style={[styles.label, { color: style.color }]}>{style.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    borderWidth: 1,
  },
  dot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
  },
  label: {
    fontSize: 10,
    fontWeight: fontWeights.bold,
    letterSpacing: 0.5,
  },
});
