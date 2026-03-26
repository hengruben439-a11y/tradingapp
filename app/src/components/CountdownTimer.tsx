import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, fontWeights } from '../theme';

interface CountdownTimerProps {
  targetTime: string;   // ISO string
  label?: string;
  onExpired?: () => void;
}

function formatDuration(ms: number): string {
  if (ms <= 0) return '00:00:00';
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds]
    .map((v) => String(v).padStart(2, '0'))
    .join(':');
}

function getColor(ms: number): string {
  const minutes = ms / 60000;
  if (minutes < 10) return colors.sellRed;
  if (minutes < 30) return colors.warning;
  return colors.textSecondary;
}

export default function CountdownTimer({ targetTime, label, onExpired }: CountdownTimerProps) {
  const [remaining, setRemaining] = useState(() =>
    Math.max(0, new Date(targetTime).getTime() - Date.now()),
  );

  useEffect(() => {
    const target = new Date(targetTime).getTime();

    const tick = () => {
      const diff = Math.max(0, target - Date.now());
      setRemaining(diff);
      if (diff === 0) {
        onExpired?.();
      }
    };

    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [targetTime, onExpired]);

  const color = getColor(remaining);

  return (
    <View style={styles.container}>
      {label && <Text style={styles.label}>{label}</Text>}
      <Text style={[styles.time, { color }]}>{formatDuration(remaining)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  label: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: fontWeights.medium,
  },
  time: {
    fontSize: 12,
    fontWeight: fontWeights.semibold,
    fontVariant: ['tabular-nums'],
  },
});
