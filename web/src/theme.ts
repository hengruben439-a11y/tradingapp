export const colors = {
  backgroundDeep: '#0A0A1A',
  backgroundCard: '#1A1A2E',
  backgroundCardAlpha: 'rgba(26,26,46,0.7)',
  ambientGradientStart: '#2D1B4E',
  ambientGradientEnd: '#1A0A2E',
  goldPrimary: '#D4A843',
  goldLight: '#E8C874',
  goldBorder: 'rgba(212,168,67,0.15)',
  goldBorderStrong: 'rgba(212,168,67,0.3)',
  buyGreen: '#22C55E',
  buyGreenAlpha: 'rgba(34,197,94,0.15)',
  sellRed: '#EF4444',
  sellRedAlpha: 'rgba(239,68,68,0.15)',
  textPrimary: '#F5F5F5',
  textSecondary: '#9CA3AF',
  textMuted: '#6B7280',
  warning: '#F59E0B',
  info: '#3B82F6',
  success: '#10B981',
  glassBackground: 'rgba(26,26,46,0.6)',
  glassBorder: 'rgba(212,168,67,0.12)',
  glassShadow: 'rgba(0,0,0,0.3)',
} as const;

export const glass = {
  background: 'rgba(26,26,46,0.6)',
  backdropFilter: 'blur(20px) saturate(150%)',
  border: '1px solid rgba(212,168,67,0.12)',
  borderRadius: '16px',
  boxShadow: '0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.05)',
} as const;

export const css = {
  glass: `
    background: rgba(26,26,46,0.6);
    backdrop-filter: blur(20px) saturate(150%);
    border: 1px solid rgba(212,168,67,0.12);
    border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.05);
  `,
};
