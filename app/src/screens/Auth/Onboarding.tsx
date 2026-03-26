import React, { useState, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Animated,
  StatusBar,
  Dimensions,
} from 'react-native';
import LinearGradient from 'react-native-linear-gradient';
import { BlurView } from '@react-native-community/blur';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { colors, spacing, typography, fontWeights, borderRadius, shadows } from '../../theme';
import * as storage from '../../services/storage';
import { useUIMode, useStore } from '../../store';
import type { UIMode, TradingStyle } from '../../types';
import type { AuthStackParamList } from '../../navigation/types';

type NavProp = StackNavigationProp<AuthStackParamList, 'Onboarding'>;

const { width: SCREEN_WIDTH } = Dimensions.get('window');

interface Step {
  title: string;
  subtitle: string;
  options: Array<{ label: string; description: string; value: string; emoji: string }>;
}

const STEPS: Step[] = [
  {
    title: 'How long have you been trading?',
    subtitle: 'This helps us tailor your experience',
    options: [
      { label: 'Just starting', emoji: '🌱', description: 'Less than 6 months', value: 'beginner' },
      { label: 'Learning', emoji: '📚', description: '6 to 18 months', value: 'intermediate' },
      { label: 'Experienced', emoji: '🎯', description: '18+ months', value: 'advanced' },
    ],
  },
  {
    title: 'What trading style suits you?',
    subtitle: 'You can change this anytime in Settings',
    options: [
      { label: 'Scalping', emoji: '⚡', description: '1-30 min trades', value: 'scalping' },
      { label: 'Day Trading', emoji: '📈', description: '1-8 hour trades', value: 'day_trading' },
      { label: 'Swing Trading', emoji: '🌊', description: '1-14 day trades', value: 'swing_trading' },
      { label: 'Position', emoji: '🏔️', description: '2-12 week trades', value: 'position_trading' },
    ],
  },
  {
    title: 'Choose your starting mode',
    subtitle: 'Upgrade anytime as you grow',
    options: [
      {
        label: 'Simple',
        emoji: '✨',
        description: 'Top signals, plain language, beginner-friendly. Recommended.',
        value: 'simple',
      },
      {
        label: 'Pro',
        emoji: '🔬',
        description: 'Full signals, module dissent, regime context. For intermediate traders.',
        value: 'pro',
      },
    ],
  },
];

export default function OnboardingScreen() {
  const navigation = useNavigation<NavProp>();
  const { setUIMode, setTradingStyle } = useUIMode();
  const [step, setStep] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [answers, setAnswers] = useState<string[]>([]);
  const slideAnim = useRef(new Animated.Value(0)).current;
  const fadeAnim = useRef(new Animated.Value(1)).current;

  const currentStep = STEPS[step];
  const isLast = step === STEPS.length - 1;

  const animateTransition = (callback: () => void) => {
    Animated.parallel([
      Animated.timing(fadeAnim, { toValue: 0, duration: 150, useNativeDriver: true }),
      Animated.timing(slideAnim, { toValue: -20, duration: 150, useNativeDriver: true }),
    ]).start(() => {
      callback();
      slideAnim.setValue(20);
      Animated.parallel([
        Animated.timing(fadeAnim, { toValue: 1, duration: 200, useNativeDriver: true }),
        Animated.timing(slideAnim, { toValue: 0, duration: 200, useNativeDriver: true }),
      ]).start();
    });
  };

  const handleNext = () => {
    if (!selected) return;
    const newAnswers = [...answers, selected];
    setAnswers(newAnswers);

    if (isLast) {
      // Apply choices
      const tradingStyle = newAnswers[1] as TradingStyle;
      const uiMode = newAnswers[2] as UIMode;
      setTradingStyle(tradingStyle);
      setUIMode(uiMode);
      storage.setOnboardingCompleted(true);
      storage.setTradingStyle(tradingStyle);
      storage.setUIMode(uiMode);

      // If guest mode, just navigate to auth
      navigation.navigate('Login');
    } else {
      animateTransition(() => {
        setStep(step + 1);
        setSelected(null);
      });
    }
  };

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" />
      <LinearGradient
        colors={[colors.backgroundDeep, colors.ambientGradientStart, colors.backgroundDeep]}
        locations={[0, 0.5, 1]}
        style={StyleSheet.absoluteFill}
      />

      {/* Progress dots */}
      <View style={styles.progressRow}>
        {STEPS.map((_, i) => (
          <View
            key={i}
            style={[
              styles.progressDot,
              i === step && styles.progressDotActive,
              i < step && styles.progressDotDone,
            ]}
          />
        ))}
      </View>

      <Animated.View
        style={[
          styles.content,
          { opacity: fadeAnim, transform: [{ translateY: slideAnim }] },
        ]}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.logo}>made.</Text>
          <Text style={styles.title}>{currentStep.title}</Text>
          <Text style={styles.subtitle}>{currentStep.subtitle}</Text>
        </View>

        {/* Options */}
        <View style={styles.optionsContainer}>
          {currentStep.options.map((opt) => (
            <TouchableOpacity
              key={opt.value}
              onPress={() => setSelected(opt.value)}
              activeOpacity={0.85}
            >
              <View
                style={[
                  styles.optionCard,
                  selected === opt.value && styles.optionCardSelected,
                ]}
              >
                <BlurView
                  style={StyleSheet.absoluteFill}
                  blurType="dark"
                  blurAmount={12}
                  reducedTransparencyFallbackColor={colors.backgroundCard}
                />
                <View style={[StyleSheet.absoluteFill, styles.optionOverlay]} />

                <Text style={styles.optionEmoji}>{opt.emoji}</Text>
                <View style={styles.optionText}>
                  <Text style={[styles.optionLabel, selected === opt.value && styles.optionLabelSelected]}>
                    {opt.label}
                  </Text>
                  <Text style={styles.optionDesc}>{opt.description}</Text>
                </View>
                {selected === opt.value && (
                  <View style={styles.checkCircle}>
                    <Text style={styles.checkText}>✓</Text>
                  </View>
                )}
              </View>
            </TouchableOpacity>
          ))}
        </View>
      </Animated.View>

      {/* CTA */}
      <View style={styles.footer}>
        <TouchableOpacity
          style={[styles.nextBtn, !selected && styles.nextBtnDisabled]}
          onPress={handleNext}
          disabled={!selected}
        >
          <LinearGradient
            colors={selected ? [colors.goldLight, colors.goldPrimary] : ['#333', '#333']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={styles.nextGradient}
          >
            <Text style={[styles.nextText, !selected && styles.nextTextDisabled]}>
              {isLast ? 'Get Started →' : 'Continue →'}
            </Text>
          </LinearGradient>
        </TouchableOpacity>

        <Text style={styles.skipNote}>
          Step {step + 1} of {STEPS.length}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.backgroundDeep,
    paddingHorizontal: spacing.lg,
    paddingTop: 60,
    paddingBottom: 40,
  },
  progressRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.sm,
    marginBottom: spacing.xxl,
  },
  progressDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.glassBorder,
  },
  progressDotActive: {
    backgroundColor: colors.goldPrimary,
    width: 24,
  },
  progressDotDone: {
    backgroundColor: colors.goldBorderStrong,
  },
  content: { flex: 1 },
  header: { marginBottom: spacing.xxl },
  logo: {
    fontSize: 22,
    fontWeight: fontWeights.bold,
    color: colors.goldPrimary,
    marginBottom: spacing.lg,
  },
  title: {
    fontSize: 26,
    fontWeight: fontWeights.bold,
    color: colors.textPrimary,
    lineHeight: 34,
    marginBottom: spacing.sm,
  },
  subtitle: {
    color: colors.textSecondary,
    fontSize: 15,
    lineHeight: 22,
  },
  optionsContainer: {
    gap: spacing.md,
  },
  optionCard: {
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    overflow: 'hidden',
    padding: spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    ...shadows.md,
  },
  optionCardSelected: {
    borderColor: colors.goldBorderStrong,
    ...shadows.gold,
  },
  optionOverlay: {
    backgroundColor: 'rgba(26,26,46,0.55)',
  },
  optionEmoji: {
    fontSize: 28,
    width: 40,
    textAlign: 'center',
  },
  optionText: { flex: 1 },
  optionLabel: {
    color: colors.textPrimary,
    fontSize: 17,
    fontWeight: fontWeights.semibold,
    marginBottom: 3,
  },
  optionLabelSelected: { color: colors.goldPrimary },
  optionDesc: {
    color: colors.textSecondary,
    fontSize: 13,
    lineHeight: 18,
  },
  checkCircle: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: 'rgba(212,168,67,0.25)',
    borderWidth: 1.5,
    borderColor: colors.goldPrimary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkText: { color: colors.goldPrimary, fontSize: 14, fontWeight: fontWeights.bold },
  footer: {
    gap: spacing.md,
  },
  nextBtn: {
    borderRadius: borderRadius.xl,
    overflow: 'hidden',
  },
  nextBtnDisabled: { opacity: 0.4 },
  nextGradient: {
    paddingVertical: spacing.lg,
    alignItems: 'center',
  },
  nextText: {
    color: '#0A0A1A',
    fontSize: 17,
    fontWeight: fontWeights.bold,
    letterSpacing: 0.3,
  },
  nextTextDisabled: { color: colors.textMuted },
  skipNote: {
    color: colors.textMuted,
    textAlign: 'center',
    fontSize: 12,
  },
});
