import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { colors } from '../theme';
import { GlassCard } from '../components/GlassCard';

interface LoginProps {
  onLogin: () => void;
}

export function Login({ onLogin }: LoginProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      onLogin();
      navigate('/');
    }, 800);
  };

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: 24, background: colors.backgroundDeep,
      position: 'relative', overflow: 'hidden',
    }}>
      {/* Ambient */}
      <div style={{
        position: 'absolute', top: -150, left: -100, width: 500, height: 500,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(45,27,78,0.7) 0%, transparent 65%)',
        pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', bottom: -100, right: -50, width: 350, height: 350,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(212,168,67,0.1) 0%, transparent 65%)',
        pointerEvents: 'none',
      }} />

      <div style={{ width: '100%', maxWidth: 380, zIndex: 1 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{ fontSize: 48, fontWeight: 800, color: colors.goldPrimary, letterSpacing: -2, lineHeight: 1 }}>
            made.
          </div>
          <div style={{ fontSize: 13, color: colors.textSecondary, marginTop: 8 }}>
            Intelligent Trading Signal Platform
          </div>
        </div>

        <GlassCard style={{ padding: 28 }}>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: colors.textPrimary, marginBottom: 20 }}>
            Sign In
          </h2>

          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 12, color: colors.textSecondary, display: 'block', marginBottom: 6 }}>
                Email Address
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="trader@example.com"
                style={{
                  width: '100%', padding: '12px 14px',
                  background: 'rgba(255,255,255,0.05)',
                  border: `1px solid ${colors.glassBorder}`,
                  borderRadius: 10, color: colors.textPrimary,
                  fontSize: 14, outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ marginBottom: 24 }}>
              <label style={{ fontSize: 12, color: colors.textSecondary, display: 'block', marginBottom: 6 }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                style={{
                  width: '100%', padding: '12px 14px',
                  background: 'rgba(255,255,255,0.05)',
                  border: `1px solid ${colors.glassBorder}`,
                  borderRadius: 10, color: colors.textPrimary,
                  fontSize: 14, outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%', padding: '14px',
                background: loading ? 'rgba(212,168,67,0.4)' : colors.goldPrimary,
                border: 'none', borderRadius: 10,
                color: colors.backgroundDeep,
                fontSize: 15, fontWeight: 700,
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'background 0.2s ease',
              }}
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>

          <div style={{
            marginTop: 20, padding: '12px 14px',
            background: 'rgba(212,168,67,0.06)',
            borderRadius: 8, border: `1px solid rgba(212,168,67,0.2)`,
          }}>
            <p style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.5 }}>
              <span style={{ color: colors.goldPrimary, fontWeight: 600 }}>Demo mode:</span> Enter any email & password to access the platform with sample data.
            </p>
          </div>
        </GlassCard>

        <p style={{ fontSize: 11, color: colors.textMuted, textAlign: 'center', marginTop: 20, lineHeight: 1.6 }}>
          Trading involves substantial risk of loss. made. provides algorithmic analysis for educational purposes only.
        </p>
      </div>
    </div>
  );
}
