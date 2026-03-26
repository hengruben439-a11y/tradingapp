import React, { useState, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Animated,
  ActivityIndicator,
  StatusBar,
} from 'react-native';
import LinearGradient from 'react-native-linear-gradient';
import { BlurView } from '@react-native-community/blur';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { colors, spacing, typography, fontWeights, borderRadius, shadows } from '../../theme';
import { auth } from '../../services/api';
import { setToken, setRefreshToken } from '../../services/storage';
import { useAuth } from '../../store';
import type { AuthStackParamList } from '../../navigation/types';

type NavProp = StackNavigationProp<AuthStackParamList, 'Login'>;

export default function LoginScreen() {
  const navigation = useNavigation<NavProp>();
  const { setAuth } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const shakeAnim = useRef(new Animated.Value(0)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(30)).current;

  React.useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, { toValue: 1, duration: 600, useNativeDriver: true }),
      Animated.spring(slideAnim, { toValue: 0, tension: 60, friction: 12, useNativeDriver: true }),
    ]).start();
  }, []);

  const shake = () => {
    Animated.sequence([
      Animated.timing(shakeAnim, { toValue: 10, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -10, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 8, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -8, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 0, duration: 60, useNativeDriver: true }),
    ]).start();
  };

  const handleLogin = async () => {
    if (!email.trim() || !password.trim()) {
      setError('Please enter your email and password.');
      shake();
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const res = await auth.login(email.trim(), password);
      setToken(res.accessToken);
      setRefreshToken(res.refreshToken);
      setAuth(res.user, res.accessToken);
    } catch (e: any) {
      setError(e?.message ?? 'Login failed. Please check your credentials.');
      shake();
    } finally {
      setIsLoading(false);
    }
  };

  const handleGuestAccess = () => {
    navigation.navigate('Onboarding');
  };

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <StatusBar barStyle="light-content" />
      <LinearGradient
        colors={[colors.backgroundDeep, colors.ambientGradientEnd, '#0A0A1A']}
        locations={[0, 0.5, 1]}
        style={StyleSheet.absoluteFill}
      />

      {/* Decorative orbs */}
      <View style={[styles.orb, styles.orb1]} />
      <View style={[styles.orb, styles.orb2]} />

      <Animated.View
        style={[
          styles.card,
          {
            opacity: fadeAnim,
            transform: [{ translateY: slideAnim }, { translateX: shakeAnim }],
          },
        ]}
      >
        <BlurView
          style={StyleSheet.absoluteFill}
          blurType="dark"
          blurAmount={20}
          reducedTransparencyFallbackColor={colors.backgroundCard}
        />
        <View style={[StyleSheet.absoluteFill, styles.cardOverlay]} />

        {/* Logo */}
        <View style={styles.logoSection}>
          <Text style={styles.logo}>made.</Text>
          <Text style={styles.logoTagline}>Intelligent Trading Signals</Text>
        </View>

        {/* Error */}
        {error && (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {/* Inputs */}
        <View style={styles.form}>
          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Email</Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder="your@email.com"
              placeholderTextColor={colors.textMuted}
              autoCapitalize="none"
              keyboardType="email-address"
              autoComplete="email"
              returnKeyType="next"
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Password</Text>
            <TextInput
              style={styles.input}
              value={password}
              onChangeText={setPassword}
              placeholder="••••••••"
              placeholderTextColor={colors.textMuted}
              secureTextEntry
              autoComplete="password"
              returnKeyType="done"
              onSubmitEditing={handleLogin}
            />
          </View>
        </View>

        {/* Sign In button */}
        <TouchableOpacity
          style={[styles.signInBtn, isLoading && styles.signInBtnDisabled]}
          onPress={handleLogin}
          disabled={isLoading}
          activeOpacity={0.85}
        >
          <LinearGradient
            colors={[colors.goldLight, colors.goldPrimary]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={styles.signInGradient}
          >
            {isLoading ? (
              <ActivityIndicator color="#0A0A1A" size="small" />
            ) : (
              <Text style={styles.signInText}>Sign In</Text>
            )}
          </LinearGradient>
        </TouchableOpacity>

        {/* Guest */}
        <TouchableOpacity style={styles.guestBtn} onPress={handleGuestAccess}>
          <Text style={styles.guestText}>Continue as Guest →</Text>
        </TouchableOpacity>

        {/* Disclaimer */}
        <Text style={styles.disclaimer}>
          Trading CFDs carries significant risk. made. provides analysis only, not financial advice.
        </Text>
      </Animated.View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.backgroundDeep,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.lg,
  },
  orb: {
    position: 'absolute',
    borderRadius: 999,
    opacity: 0.5,
  },
  orb1: {
    width: 320,
    height: 320,
    backgroundColor: colors.ambientGradientStart,
    top: -100,
    right: -100,
  },
  orb2: {
    width: 240,
    height: 240,
    backgroundColor: '#1A0A3E',
    bottom: -60,
    left: -80,
  },
  card: {
    width: '100%',
    maxWidth: 380,
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: colors.goldBorder,
    overflow: 'hidden',
    padding: spacing.xxl,
    ...shadows.gold,
  },
  cardOverlay: {
    backgroundColor: 'rgba(26,26,46,0.65)',
  },
  logoSection: {
    alignItems: 'center',
    marginBottom: spacing.xxl,
  },
  logo: {
    fontSize: 44,
    fontWeight: fontWeights.bold,
    color: colors.goldPrimary,
    letterSpacing: -1,
  },
  logoTagline: {
    color: colors.textSecondary,
    fontSize: 13,
    fontWeight: fontWeights.medium,
    letterSpacing: 0.5,
    marginTop: spacing.xs,
  },
  errorBox: {
    backgroundColor: 'rgba(239,68,68,0.1)',
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: 'rgba(239,68,68,0.3)',
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  errorText: {
    color: colors.sellRed,
    fontSize: 13,
    textAlign: 'center',
  },
  form: {
    gap: spacing.md,
    marginBottom: spacing.lg,
  },
  inputGroup: {
    gap: spacing.xs,
  },
  inputLabel: {
    color: colors.textSecondary,
    fontSize: 12,
    fontWeight: fontWeights.semibold,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  input: {
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    padding: spacing.md,
    color: colors.textPrimary,
    fontSize: 16,
  },
  signInBtn: {
    borderRadius: borderRadius.xl,
    overflow: 'hidden',
    marginBottom: spacing.md,
  },
  signInBtnDisabled: { opacity: 0.6 },
  signInGradient: {
    paddingVertical: spacing.lg,
    alignItems: 'center',
  },
  signInText: {
    color: '#0A0A1A',
    fontSize: 17,
    fontWeight: fontWeights.bold,
    letterSpacing: 0.3,
  },
  guestBtn: {
    alignItems: 'center',
    paddingVertical: spacing.md,
  },
  guestText: {
    color: colors.textSecondary,
    fontSize: 14,
    fontWeight: fontWeights.medium,
  },
  disclaimer: {
    color: colors.textMuted,
    fontSize: 11,
    textAlign: 'center',
    lineHeight: 16,
    marginTop: spacing.md,
  },
});
