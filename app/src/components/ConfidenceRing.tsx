import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { colors, fontSizes, fontWeights } from '../theme';

interface ConfidenceRingProps {
  score: number;    // 0 to 1
  size?: number;
  color?: string;
  showLabel?: boolean;
}

function getScoreColor(score: number): string {
  if (score >= 0.8) return colors.goldPrimary;
  if (score >= 0.65) return colors.goldLight;
  if (score >= 0.5) return colors.warning;
  return colors.textMuted;
}

export default function ConfidenceRing({
  score,
  size = 64,
  color,
  showLabel = true,
}: ConfidenceRingProps) {
  const animatedValue = useRef(new Animated.Value(0)).current;
  const ringColor = color ?? getScoreColor(score);

  const strokeWidth = size * 0.1;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const cx = size / 2;
  const cy = size / 2;

  useEffect(() => {
    Animated.timing(animatedValue, {
      toValue: score,
      duration: 800,
      useNativeDriver: false,
    }).start();
  }, [score, animatedValue]);

  const strokeDashoffset = animatedValue.interpolate({
    inputRange: [0, 1],
    outputRange: [circumference, 0],
  });

  const percentage = Math.round(score * 100);

  return (
    <View style={[styles.container, { width: size, height: size }]}>
      <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
        {/* Track */}
        <Circle
          cx={cx}
          cy={cy}
          r={radius}
          stroke={colors.textMuted}
          strokeOpacity={0.2}
          strokeWidth={strokeWidth}
          fill="none"
        />
        {/* Progress — we use a plain Circle since AnimatedCircle isn't available */}
        <Circle
          cx={cx}
          cy={cy}
          r={radius}
          stroke={ringColor}
          strokeWidth={strokeWidth}
          fill="none"
          strokeDasharray={`${circumference} ${circumference}`}
          strokeDashoffset={circumference * (1 - score)}
          strokeLinecap="round"
          rotation="-90"
          origin={`${cx}, ${cy}`}
        />
      </Svg>
      {showLabel && (
        <View style={styles.labelContainer}>
          <Text style={[styles.percentage, { color: ringColor, fontSize: size * 0.22 }]}>
            {percentage}
          </Text>
          <Text style={[styles.pct, { fontSize: size * 0.14, color: ringColor }]}>%</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  labelContainer: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  percentage: {
    fontWeight: fontWeights.bold,
  },
  pct: {
    fontWeight: fontWeights.medium,
  },
});
