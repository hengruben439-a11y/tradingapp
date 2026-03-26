import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { colors } from '../theme';

interface LayoutProps {
  children: React.ReactNode;
}

const NAV_ITEMS = [
  { path: '/', label: 'Signals', icon: SignalIcon },
  { path: '/calendar', label: 'Calendar', icon: CalendarIcon },
  { path: '/journal', label: 'Journal', icon: JournalIcon },
  { path: '/settings', label: 'Settings', icon: SettingsIcon },
];

export function Layout({ children }: LayoutProps) {
  const location = useLocation();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', maxWidth: 480, margin: '0 auto', position: 'relative' }}>
      {/* Ambient orbs */}
      <div style={{
        position: 'fixed', top: -100, left: -100, width: 400, height: 400,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(45,27,78,0.6) 0%, transparent 70%)',
        pointerEvents: 'none', zIndex: 0,
      }} />
      <div style={{
        position: 'fixed', bottom: 100, right: -80, width: 300, height: 300,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(212,168,67,0.08) 0%, transparent 70%)',
        pointerEvents: 'none', zIndex: 0,
      }} />

      {/* Header */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 100,
        padding: '16px 20px 12px',
        background: 'rgba(10,10,26,0.85)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderBottom: `1px solid ${colors.glassBorder}`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div>
          <span style={{ fontSize: 22, fontWeight: 800, color: colors.goldPrimary, letterSpacing: -0.5 }}>made.</span>
          <span style={{ fontSize: 11, color: colors.textMuted, marginLeft: 8 }}>
            {NAV_ITEMS.find(n => n.path === location.pathname)?.label ?? 'Platform'}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: colors.buyGreen,
            boxShadow: `0 0 6px ${colors.buyGreen}`,
          }} />
          <span style={{ fontSize: 11, color: colors.textMuted }}>LIVE</span>
        </div>
      </header>

      {/* Content */}
      <main style={{ flex: 1, padding: '16px 16px 100px', position: 'relative', zIndex: 1 }}>
        {children}
      </main>

      {/* Bottom Nav */}
      <nav style={{
        position: 'fixed', bottom: 0, left: '50%', transform: 'translateX(-50%)',
        width: '100%', maxWidth: 480,
        background: 'rgba(26,26,46,0.92)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderTop: `1px solid ${colors.glassBorder}`,
        display: 'flex',
        zIndex: 100,
        paddingBottom: 8,
      }}>
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            style={({ isActive }) => ({
              flex: 1, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              padding: '10px 0 4px',
              textDecoration: 'none',
              color: isActive ? colors.goldPrimary : colors.textMuted,
              transition: 'color 0.15s ease',
            })}
          >
            {({ isActive }) => (
              <>
                <Icon size={22} active={isActive} />
                <span style={{ fontSize: 10, fontWeight: 500, marginTop: 3 }}>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

// ── Icon components ──────────────────────────────────────────────────────────

function SignalIcon({ size, active }: { size: number; active: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M3 12L12 3L21 12V20C21 20.55 20.55 21 20 21H15V16H9V21H4C3.45 21 3 20.55 3 20V12Z"
        stroke="currentColor" strokeWidth={active ? 2.2 : 1.8} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CalendarIcon({ size, active }: { size: number; active: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M8 2V6M16 2V6M3 10H21M5 4H19C20.1 4 21 4.9 21 6V20C21 21.1 20.1 22 19 22H5C3.9 22 3 21.1 3 20V6C3 4.9 3.9 4 5 4Z"
        stroke="currentColor" strokeWidth={active ? 2.2 : 1.8} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function JournalIcon({ size, active }: { size: number; active: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M4 19.5C4 18.1 5.1 17 6.5 17H20M4 19.5C4 20.9 5.1 22 6.5 22H20V2H6.5C5.1 2 4 3.1 4 4.5V19.5Z"
        stroke="currentColor" strokeWidth={active ? 2.2 : 1.8} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SettingsIcon({ size, active }: { size: number; active: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx={12} cy={12} r={3} stroke="currentColor" strokeWidth={active ? 2.2 : 1.8} />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
        stroke="currentColor" strokeWidth={active ? 2.2 : 1.8} />
    </svg>
  );
}
