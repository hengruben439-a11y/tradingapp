import React, { useEffect } from 'react';
import { View, StyleSheet } from 'react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import LinearGradient from 'react-native-linear-gradient';

import { colors } from './src/theme';
import RootNavigator from './src/navigation';
import { initWebSocket, closeWebSocket } from './src/services/websocket';
import { useAuth } from './src/store';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 30_000,
      gcTime: 5 * 60_000,
    },
    mutations: {
      retry: 1,
    },
  },
});

function AppContent() {
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    if (isAuthenticated) {
      initWebSocket();
    } else {
      closeWebSocket();
    }
    return () => {
      closeWebSocket();
    };
  }, [isAuthenticated]);

  return (
    <View style={styles.root}>
      {/* Deep background gradient */}
      <LinearGradient
        colors={[colors.backgroundDeep, colors.ambientGradientEnd, colors.backgroundDeep]}
        locations={[0, 0.4, 1]}
        style={StyleSheet.absoluteFill}
        pointerEvents="none"
      />
      <RootNavigator />
    </View>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SafeAreaProvider>
        <AppContent />
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.backgroundDeep,
  },
});
