import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { SignalDetail } from './pages/SignalDetail';
import { Calendar } from './pages/Calendar';
import { Journal } from './pages/Journal';
import { Settings } from './pages/Settings';
import { RiskCalculator } from './pages/RiskCalculator';

function AppLayout() {
  return (
    <Layout>
      <Outlet />
    </Layout>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(false);

  if (!authed) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="*" element={<Login onLogin={() => setAuthed(true)} />} />
        </Routes>
      </BrowserRouter>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/signal/:id" element={<SignalDetail />} />
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/journal" element={<Journal />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/risk" element={<RiskCalculator />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
