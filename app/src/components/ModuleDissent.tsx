import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, fontWeights } from '../theme';
import { useUIMode } from '../store';

interface ModuleScore {
  module: string;
  score: number;   // -1 to +1
  weight: number;  // 0 to 1 (e.g. 0.25 = 25%)
}

interface ModuleDissentProps {
  modules: ModuleScore[];
}

const MODULE_LABELS: Record<string, string> = {
  market_structure: 'Market Structure',
  ob_fvg: 'OB / FVG',
  ote_fibonacci: 'OTE Fibonacci',
  ema_alignment: 'EMA Alignment',
  rsi: 'RSI',
  macd: 'MACD',
  bollinger_bands: 'Bollinger Bands',
  kill_zone: 'Kill Zone',
  sr_liquidity: 'S&R / Liquidity',
};

function getBarColor(score: number): string {
  if (score > 0.2) return colors.buyGreen;
  if (score < -0.2) return colors.sellRed;
  return colors.warning;
}

function getBarLabel(score: number): string {
  if (score > 0.2) return 'aligned';
  if (score < -0.2) return 'opposing';
  return 'neutral';
}

export default function ModuleDissent({ modules }: ModuleDissentProps) {
  const { isMaxMode } = useUIMode();

  // Sort by absolute score descending
  const sorted = [...modules].sort((a, b) => Math.abs(b.score) - Math.abs(a.score));

  return (
    <View style={styles.container}>
      {sorted.map((mod) => {
        const label = MODULE_LABELS[mod.module] ?? mod.module;
        const barColor = getBarColor(mod.score);
        const barWidth = `${Math.abs(mod.score) * 100}%`;
        const isOpposing = mod.score < -0.2;

        return (
          <View key={mod.module} style={styles.row}>
            <View style={styles.labelGroup}>
              <Text style={[styles.moduleName, isOpposing && styles.moduleNameOpposing]}>
                {label}
              </Text>
              <Text style={styles.weight}>{Math.round(mod.weight * 100)}%</Text>
            </View>
            <View style={styles.barTrack}>
              {/* Center line */}
              <View style={styles.centerLine} />
              {/* Bar */}
              <View
                style={[
                  styles.bar,
                  {
                    width: barWidth,
                    backgroundColor: barColor,
                    alignSelf: mod.score >= 0 ? 'flex-start' : 'flex-end',
                    left: mod.score >= 0 ? '50%' : undefined,
                    right: mod.score < 0 ? '50%' : undefined,
                  },
                ]}
              />
            </View>
            {isMaxMode && (
              <Text style={[styles.scoreText, { color: barColor }]}>
                {mod.score > 0 ? '+' : ''}{mod.score.toFixed(2)}
              </Text>
            )}
          </View>
        );
      })}

      {/* Dissent summary */}
      {(() => {
        const opposing = sorted.filter((m) => m.score < -0.2);
        if (opposing.length === 0) return null;
        return (
          <View style={styles.dissentSummary}>
            <Text style={styles.dissentLabel}>Dissent</Text>
            {opposing.map((mod) => (
              <Text key={mod.module} style={styles.dissentItem}>
                • {MODULE_LABELS[mod.module] ?? mod.module} ({Math.round(mod.weight * 100)}% weight) opposes this signal
              </Text>
            ))}
          </View>
        );
      })()}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  labelGroup: {
    width: 120,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  moduleName: {
    color: colors.textSecondary,
    fontSize: 12,
    fontWeight: fontWeights.medium,
    flex: 1,
  },
  moduleNameOpposing: {
    color: colors.sellRed,
  },
  weight: {
    color: colors.textMuted,
    fontSize: 11,
    marginLeft: spacing.xs,
  },
  barTrack: {
    flex: 1,
    height: 8,
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderRadius: 4,
    overflow: 'hidden',
    position: 'relative',
  },
  centerLine: {
    position: 'absolute',
    left: '50%',
    top: 0,
    bottom: 0,
    width: 1,
    backgroundColor: 'rgba(255,255,255,0.15)',
  },
  bar: {
    position: 'absolute',
    height: '100%',
    borderRadius: 4,
    opacity: 0.85,
  },
  scoreText: {
    width: 36,
    fontSize: 11,
    fontWeight: fontWeights.semibold,
    textAlign: 'right',
  },
  dissentSummary: {
    marginTop: spacing.sm,
    padding: spacing.sm,
    backgroundColor: 'rgba(239,68,68,0.08)',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(239,68,68,0.2)',
  },
  dissentLabel: {
    color: colors.sellRed,
    fontSize: 11,
    fontWeight: fontWeights.bold,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: spacing.xs,
  },
  dissentItem: {
    color: colors.textSecondary,
    fontSize: 12,
    lineHeight: 18,
  },
});
