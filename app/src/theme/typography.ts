import { StyleSheet } from 'react-native';

export const fontSizes = {
  displayLarge: 32,
  displayMedium: 24,
  headingLarge: 20,
  headingMedium: 18,
  headingSmall: 16,
  bodyLarge: 15,
  bodyMedium: 14,
  bodySmall: 13,
  caption: 12,
  label: 11,
} as const;

export const fontWeights = {
  regular: '400' as const,
  medium: '500' as const,
  semibold: '600' as const,
  bold: '700' as const,
};

export const lineHeights = {
  displayLarge: 40,
  displayMedium: 32,
  headingLarge: 28,
  headingMedium: 26,
  headingSmall: 24,
  bodyLarge: 22,
  bodyMedium: 20,
  bodySmall: 19,
  caption: 18,
  label: 16,
} as const;

export const typography = StyleSheet.create({
  displayLarge: {
    fontSize: fontSizes.displayLarge,
    fontWeight: fontWeights.bold,
    lineHeight: lineHeights.displayLarge,
  },
  displayMedium: {
    fontSize: fontSizes.displayMedium,
    fontWeight: fontWeights.bold,
    lineHeight: lineHeights.displayMedium,
  },
  headingLarge: {
    fontSize: fontSizes.headingLarge,
    fontWeight: fontWeights.semibold,
    lineHeight: lineHeights.headingLarge,
  },
  headingMedium: {
    fontSize: fontSizes.headingMedium,
    fontWeight: fontWeights.semibold,
    lineHeight: lineHeights.headingMedium,
  },
  headingSmall: {
    fontSize: fontSizes.headingSmall,
    fontWeight: fontWeights.semibold,
    lineHeight: lineHeights.headingSmall,
  },
  bodyLarge: {
    fontSize: fontSizes.bodyLarge,
    fontWeight: fontWeights.regular,
    lineHeight: lineHeights.bodyLarge,
  },
  bodyMedium: {
    fontSize: fontSizes.bodyMedium,
    fontWeight: fontWeights.regular,
    lineHeight: lineHeights.bodyMedium,
  },
  bodySmall: {
    fontSize: fontSizes.bodySmall,
    fontWeight: fontWeights.regular,
    lineHeight: lineHeights.bodySmall,
  },
  caption: {
    fontSize: fontSizes.caption,
    fontWeight: fontWeights.regular,
    lineHeight: lineHeights.caption,
  },
  label: {
    fontSize: fontSizes.label,
    fontWeight: fontWeights.medium,
    lineHeight: lineHeights.label,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
  },
});
