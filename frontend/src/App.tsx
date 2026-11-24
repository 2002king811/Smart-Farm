import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { BrowserRouter } from 'react-router-dom';

import { ToastProvider } from '@/components/Toast';
import { SessionProvider } from '@/features/session/SessionContext';
import { AppRoutes } from '@/routes/AppRoutes';

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      // "always": requests still run offline, and the API client answers from saved data.
      queries: { staleTime: 30_000, refetchOnWindowFocus: false, networkMode: 'always' },
      mutations: { networkMode: 'always' },
    },
  });
}

export function Providers({ children, client }: { children: ReactNode; client?: QueryClient }) {
  const [queryClient] = useState(() => client ?? makeQueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <ToastProvider>{children}</ToastProvider>
      </SessionProvider>
    </QueryClientProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Providers>
        <AppRoutes />
      </Providers>
    </BrowserRouter>
  );
}
