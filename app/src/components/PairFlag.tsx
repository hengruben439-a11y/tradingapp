import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, fontWeights } from '../theme';

interface PairFlagProps {
  pair: 'XAUUSD' | 'GBPJPY' | string;
  size?: 'sm' | 'md' | 'lg';
}

const PAIR_CONFIG: Record<string, { emoji: string; label: string; accent: string }> = {
  XAUUSD: {
    emoji: '🥇',
    label: 'XAU/USD',
    accent: colors.goldPrimary,
  },
  GBPJPY: {
    emoji: '🇬🇧🇯🇵',
    label: 'GBP/JPY',
    accent: colors.info,
  },
};

const SIZE_CONFIG = {
  sm: { emoji: 14, label: 12, padding: 4 },
  md: { emoji: 18, label: 14, padding: 6 },
  lg: { emoji: 22, label: 17, padding: 8 },
};

export default function PairFlag({ pair, size = 'md' }: PairFlagProps) {
  const config = PAIR_CONFIG[pair] ?? {
    emoji: '💱',
    label: pair,
    accent: colors.textSecondary,
  };
  const sizeConfig = SIZE_CONFIG[size];

  return (
    <View style={[styles.container, { paddingVertical: sizeConfig.padding / 2 }]}>
      <Text style={{ fontSize: sizeConfig.emoji }}>{config.emoji}</Text>
      <Text
        style={[
          styles.label,
          {
            fontSize: sizeConfig.label,
            color: config.accent,
          },
        ]}
      >
        {config.label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  label: {
    fontWeight: fontWeights.semibold,
    letterSpacing: 0.3,
  },
});
