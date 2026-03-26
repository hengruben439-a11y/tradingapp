import React from 'react';
import {
  View,
  TouchableOpacity,
  StyleSheet,
  ViewStyle,
  StyleProp,
} from 'react-native';
import { BlurView } from '@react-native-community/blur';
import { colors, borderRadius, spacing, shadows } from '../theme';

interface GlassCardProps {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
  padding?: number;
  borderHighlight?: boolean;
  disabled?: boolean;
}

export default function GlassCard({
  children,
  style,
  onPress,
  padding = spacing.lg,
  borderHighlight = false,
  disabled = false,
}: GlassCardProps) {
  const containerStyle = [
    styles.container,
    borderHighlight && styles.highlighted,
    { padding },
    style,
  ];

  const inner = (
    <>
      <BlurView
        style={StyleSheet.absoluteFill}
        blurType="dark"
        blurAmount={20}
        reducedTransparencyFallbackColor={colors.backgroundCard}
      />
      <View style={styles.overlay} />
      {children}
    </>
  );

  if (onPress) {
    return (
      <TouchableOpacity
        style={containerStyle}
        onPress={onPress}
        activeOpacity={0.85}
        disabled={disabled}
      >
        {inner}
      </TouchableOpacity>
    );
  }

  return <View style={containerStyle}>{inner}</View>;
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.glassBackground,
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    overflow: 'hidden',
    ...shadows.md,
  },
  highlighted: {
    borderColor: colors.goldBorderStrong,
    ...shadows.gold,
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: colors.glassBackground,
  },
});
