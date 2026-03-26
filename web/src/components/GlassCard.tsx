import React from 'react';
import { colors } from '../theme';

interface GlassCardProps {
  children: React.ReactNode;
  style?: React.CSSProperties;
  highlighted?: boolean;
  onClick?: () => void;
  className?: string;
}

export function GlassCard({ children, style, highlighted, onClick, className }: GlassCardProps) {
  return (
    <div
      className={className}
      onClick={onClick}
      style={{
        background: 'rgba(26,26,46,0.6)',
        backdropFilter: 'blur(20px) saturate(150%)',
        WebkitBackdropFilter: 'blur(20px) saturate(150%)',
        border: `1px solid ${highlighted ? colors.goldPrimary : colors.glassBorder}`,
        borderRadius: '16px',
        boxShadow: highlighted
          ? `0 8px 32px rgba(0,0,0,0.3), 0 0 20px rgba(212,168,67,0.15), inset 0 1px 0 rgba(255,255,255,0.05)`
          : '0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.05)',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'transform 0.15s ease, box-shadow 0.15s ease',
        ...style,
      }}
    >
      {children}
    </div>
  );
}
