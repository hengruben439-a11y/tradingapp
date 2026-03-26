/**
 * Subscription / Paywall Screen
 *
 * Shows Free / Premium / Pro tiers with pricing per CLAUDE.md §19.2.
 * Handles Apple In-App Purchase flow (IAP) via react-native-iap.
 * Gate: Pro mode features redirect here if user is on Free tier.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Pressable,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import Svg, { Path, Circle } from 'react-native-svg';

import { colors, spacing, typography, borderRadius } from '../../theme';
import GlassCard from '../../components/GlassCard';
import { useAuth } from '../../store';
import type { RootStackParamList } from '../../navigation/types';

type SubscriptionRoute = RouteProp<RootStackParamList, 'Subscription'>;

// ── Tier data ─────────────────────────────────────────────────────────────────

interface TierFeature {
  text: string;
  available: boolean;
}

interface Tier {
  id: 'free' | 'premium' | 'pro';
  name: string;
  monthlyPrice: number;
  annualPrice: number;
  annualSavingsPct: number;
  tagline: string;
  features: TierFeature[];
  highlighted: boolean;
  productIdMonthly: string;
  productIdAnnual: string;
}

const TIERS: Tier[] = [
  {
    id: 'free',
    name: 'Free',
    monthlyPrice: 0,
    annualPrice: 0,
    annualSavingsPct: 0,
    tagline: 'Explore the platform',
    productIdMonthly: '',
    productIdAnnual: '',
    highlighted: false,
    features: [
      { text: 'Signal ideas (no entry/TP/SL levels)', available: true },
      { text: 'Economic calendar', available: true },
      { text: 'Contextual tooltips', available: true },
      { text: '1H timeframe only', available: true },
      { text: 'Paper trading mode', available: true },
      { text: 'Full signals with TP/SL', available: false },
      { text: 'Push & Telegram alerts', available: false },
      { text: 'Trade journal + post-mortems', available: false },
    ],
  },
  {
    id: 'premium',
    name: 'Premium',
    monthlyPrice: 49,
    annualPrice: 399,
    annualSavingsPct: 32,
    tagline: 'Everything you need to trade',
    productIdMonthly: 'com.made.trading.premium.monthly',
    productIdAnnual: 'com.made.trading.premium.annual',
    highlighted: true,
    features: [
      { text: 'Full signals — all timeframes', available: true },
      { text: 'Entry, TP1/TP2/TP3, SL with R:R', available: true },
      { text: 'Push & Telegram alerts', available: true },
      { text: 'Trade journal with post-mortems', available: true },
      { text: 'Risk calculator', available: true },
      { text: 'News reaction data', available: true },
      { text: 'Simple & Pro UI modes', available: true },
      { text: 'Max mode + raw module scores', available: false },
      { text: 'Broker execution (MetaApi)', available: false },
    ],
  },
  {
    id: 'pro',
    name: 'Pro',
    monthlyPrice: 99,
    annualPrice: 799,
    annualSavingsPct: 33,
    tagline: 'For serious traders',
    productIdMonthly: 'com.made.trading.pro.monthly',
    productIdAnnual: 'com.made.trading.pro.annual',
    highlighted: false,
    features: [
      { text: 'Everything in Premium', available: true },
      { text: 'Broker execution (HFM MT4/MT5)', available: true },
      { text: 'Custom Expert Advisor (EA)', available: true },
      { text: 'Max UI mode + raw scores', available: true },
      { text: 'Advanced analytics (Sharpe/Calmar)', available: true },
      { text: 'Backtest report access', available: true },
      { text: 'Priority signal delivery (<500ms)', available: true },
      { text: 'CSV export', available: true },
    ],
  },
];

// ── Sub-components ────────────────────────────────────────────────────────────

function CheckIcon({ available }: { available: boolean }) {
  return (
    <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
      {available ? (
        <>
          <Circle cx={12} cy={12} r={10} fill={colors.buyGreenAlpha} />
          <Path
            d="M8 12L11 15L16 9"
            stroke={colors.buyGreen}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      ) : (
        <>
          <Circle cx={12} cy={12} r={10} fill="rgba(107,114,128,0.15)" />
          <Path
            d="M9 9L15 15M15 9L9 15"
            stroke={colors.textMuted}
            strokeWidth={1.5}
            strokeLinecap="round"
          />
        </>
      )}
    </Svg>
  );
}

function TierCard({
  tier,
  isAnnual,
  isCurrentTier,
  onSelect,
  loading,
}: {
  tier: Tier;
  isAnnual: boolean;
  isCurrentTier: boolean;
  onSelect: (tier: Tier) => void;
  loading: boolean;
}) {
  const price = isAnnual
    ? (tier.annualPrice / 12).toFixed(0)
    : tier.monthlyPrice.toFixed(0);
  const billingNote = isAnnual
    ? `$${tier.annualPrice}/year`
    : 'per month';

  return (
    <GlassCard
      style={[styles.tierCard, tier.highlighted && styles.tierCardHighlighted]}
      borderHighlight={tier.highlighted}
    >
      {tier.highlighted && (
        <View style={styles.popularBadge}>
          <Text style={styles.popularText}>MOST POPULAR</Text>
        </View>
      )}

      <View style={styles.tierHeader}>
        <Text style={styles.tierName}>{tier.name}</Text>
        <Text style={styles.tierTagline}>{tier.tagline}</Text>
      </View>

      <View style={styles.priceRow}>
        {tier.monthlyPrice === 0 ? (
          <Text style={styles.priceText}>Free</Text>
        ) : (
          <>
            <Text style={styles.priceText}>${price}</Text>
            <Text style={styles.priceUnit}>/mo</Text>
          </>
        )}
      </View>

      {isAnnual && tier.annualPrice > 0 && (
        <Text style={styles.billingNote}>
          {billingNote} · Save {tier.annualSavingsPct}%
        </Text>
      )}

      <View style={styles.featureList}>
        {tier.features.map((f, i) => (
          <View key={i} style={styles.featureRow}>
            <CheckIcon available={f.available} />
            <Text
              style={[
                styles.featureText,
                !f.available && styles.featureTextDisabled,
              ]}
            >
              {f.text}
            </Text>
          </View>
        ))}
      </View>

      {isCurrentTier ? (
        <View style={styles.currentPlanButton}>
          <Text style={styles.currentPlanText}>Current Plan</Text>
        </View>
      ) : tier.id === 'free' ? (
        <View style={styles.freePlanNote}>
          <Text style={styles.freePlanText}>No payment required</Text>
        </View>
      ) : (
        <TouchableOpacity
          style={[
            styles.subscribeButton,
            tier.highlighted && styles.subscribeButtonHighlighted,
          ]}
          onPress={() => onSelect(tier)}
          disabled={loading}
          activeOpacity={0.8}
        >
          {loading ? (
            <ActivityIndicator size="small" color={colors.backgroundDeep} />
          ) : (
            <Text
              style={[
                styles.subscribeButtonText,
                tier.highlighted && styles.subscribeButtonTextHighlighted,
              ]}
            >
              {`Subscribe to ${tier.name}`}
            </Text>
          )}
        </TouchableOpacity>
      )}
    </GlassCard>
  );
}

// ── Main screen ───────────────────────────────────────────────────────────────

export default function SubscriptionScreen() {
  const navigation = useNavigation();
  const { user } = useAuth();
  const [isAnnual, setIsAnnual] = useState(true);
  const [loading, setLoading] = useState<string | null>(null);

  const currentTier = user?.subscriptionTier ?? 'free';

  const handleSelect = async (tier: Tier) => {
    if (tier.id === 'free') return;
    const productId = isAnnual ? tier.productIdAnnual : tier.productIdMonthly;
    setLoading(tier.id);
    try {
      // In production: use react-native-iap to initiate purchase
      // await RNIap.requestPurchase({ sku: productId });
      // For now, navigate back — real IAP wired in Phase 4
      console.log('Initiating purchase for:', productId);
    } catch (e) {
      console.error('Purchase failed:', e);
    } finally {
      setLoading(null);
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Pressable style={styles.closeButton} onPress={() => navigation.goBack()}>
          <Svg width={24} height={24} viewBox="0 0 24 24" fill="none">
            <Path
              d="M18 6L6 18M6 6L18 18"
              stroke={colors.textSecondary}
              strokeWidth={2}
              strokeLinecap="round"
            />
          </Svg>
        </Pressable>
        <View>
          <Text style={styles.title}>made. Plans</Text>
          <Text style={styles.subtitle}>Transparent pricing. No hidden fees.</Text>
        </View>
      </View>

      {/* Annual / Monthly toggle */}
      <View style={styles.billingToggle}>
        <TouchableOpacity
          style={[styles.toggleOption, !isAnnual && styles.toggleOptionActive]}
          onPress={() => setIsAnnual(false)}
        >
          <Text style={[styles.toggleText, !isAnnual && styles.toggleTextActive]}>
            Monthly
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.toggleOption, isAnnual && styles.toggleOptionActive]}
          onPress={() => setIsAnnual(true)}
        >
          <Text style={[styles.toggleText, isAnnual && styles.toggleTextActive]}>
            Annual
          </Text>
          <View style={styles.savingsBadge}>
            <Text style={styles.savingsText}>Save 32%</Text>
          </View>
        </TouchableOpacity>
      </View>

      {/* Tier cards */}
      <ScrollView
        contentContainerStyle={styles.tiersContainer}
        showsVerticalScrollIndicator={false}
      >
        {TIERS.map(tier => (
          <TierCard
            key={tier.id}
            tier={tier}
            isAnnual={isAnnual}
            isCurrentTier={currentTier === tier.id}
            onSelect={handleSelect}
            loading={loading === tier.id}
          />
        ))}

        {/* Disclaimer */}
        <Text style={styles.disclaimer}>
          Subscriptions auto-renew. Cancel anytime in App Store Settings.
          Prices in USD. Trading involves substantial risk of loss.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.backgroundDeep,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing[4],
    paddingTop: spacing[3],
    paddingBottom: spacing[4],
    gap: spacing[3],
  },
  closeButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.06)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    ...typography.headingLarge,
    color: colors.textPrimary,
  },
  subtitle: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    marginTop: 2,
  },
  billingToggle: {
    flexDirection: 'row',
    marginHorizontal: spacing[4],
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: borderRadius.lg,
    padding: 4,
    marginBottom: spacing[4],
  },
  toggleOption: {
    flex: 1,
    paddingVertical: spacing[2],
    alignItems: 'center',
    borderRadius: borderRadius.md,
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing[2],
  },
  toggleOptionActive: {
    backgroundColor: colors.goldPrimary,
  },
  toggleText: {
    ...typography.bodyMedium,
    fontWeight: '600',
    color: colors.textSecondary,
  },
  toggleTextActive: {
    color: colors.backgroundDeep,
  },
  savingsBadge: {
    backgroundColor: colors.buyGreen,
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  savingsText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#fff',
  },
  tiersContainer: {
    paddingHorizontal: spacing[4],
    paddingBottom: spacing[8],
    gap: spacing[4],
  },
  tierCard: {
    padding: spacing[5],
  },
  tierCardHighlighted: {
    borderColor: colors.goldPrimary,
  },
  popularBadge: {
    alignSelf: 'flex-start',
    backgroundColor: colors.goldPrimary,
    borderRadius: 6,
    paddingHorizontal: spacing[2],
    paddingVertical: 3,
    marginBottom: spacing[3],
  },
  popularText: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.backgroundDeep,
    letterSpacing: 0.5,
  },
  tierHeader: {
    marginBottom: spacing[3],
  },
  tierName: {
    ...typography.headingMedium,
    color: colors.textPrimary,
    fontWeight: '700',
  },
  tierTagline: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    marginTop: 2,
  },
  priceRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 4,
    marginBottom: 2,
  },
  priceText: {
    fontSize: 36,
    fontWeight: '700',
    color: colors.goldPrimary,
    lineHeight: 42,
  },
  priceUnit: {
    ...typography.bodyMedium,
    color: colors.textSecondary,
  },
  billingNote: {
    ...typography.caption,
    color: colors.textMuted,
    marginBottom: spacing[4],
  },
  featureList: {
    gap: spacing[2],
    marginBottom: spacing[4],
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[2],
  },
  featureText: {
    ...typography.bodySmall,
    color: colors.textPrimary,
    flex: 1,
  },
  featureTextDisabled: {
    color: colors.textMuted,
  },
  subscribeButton: {
    backgroundColor: 'rgba(212,168,67,0.15)',
    borderWidth: 1,
    borderColor: colors.goldPrimary,
    borderRadius: borderRadius.md,
    paddingVertical: spacing[3],
    alignItems: 'center',
  },
  subscribeButtonHighlighted: {
    backgroundColor: colors.goldPrimary,
  },
  subscribeButtonText: {
    ...typography.bodyMedium,
    fontWeight: '600',
    color: colors.goldPrimary,
  },
  subscribeButtonTextHighlighted: {
    color: colors.backgroundDeep,
  },
  currentPlanButton: {
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: borderRadius.md,
    paddingVertical: spacing[3],
    alignItems: 'center',
  },
  currentPlanText: {
    ...typography.bodyMedium,
    color: colors.textSecondary,
  },
  freePlanNote: {
    paddingVertical: spacing[3],
    alignItems: 'center',
  },
  freePlanText: {
    ...typography.bodySmall,
    color: colors.textMuted,
  },
  disclaimer: {
    ...typography.caption,
    color: colors.textMuted,
    textAlign: 'center',
    paddingHorizontal: spacing[4],
    lineHeight: 18,
  },
});
