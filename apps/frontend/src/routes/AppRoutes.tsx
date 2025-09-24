import { BrowserRouter, Routes, Route } from 'react-router-dom';
import RequireAuth from './RequireAuth';
import LoginPage from '../features/auth/pages/LoginPage';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';

const queryClient = new QueryClient();

function Dashboard() {
  return (
    <div className="min-h-dvh bg-gradient-to-br from-emerald-950 via-emerald-900 to-emerald-950 px-6 py-16">
      <div className="mx-auto flex max-w-2xl flex-col items-center justify-center gap-6 text-center">
        <span className="rounded-full border border-white/10 bg-white/10 px-4 py-1 text-xs font-medium uppercase tracking-[0.3em] text-emerald-100">
          Panel principal
        </span>
        <h1 className="text-4xl font-semibold text-white sm:text-5xl">Bienvenido al portal Evalutia</h1>
        <p className="text-lg leading-relaxed text-emerald-100/90">
          Gestiona y visualiza tus métricas clave en un entorno claro, moderno y enfocado
          en lo que realmente importa.
        </p>
      </div>
    </div>
  );
}

export default function AppRoutes() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* públicas */}
          <Route path="/login" element={<LoginPage />} />
          {/* privadas */}
          <Route element={<RequireAuth />}>
            <Route path="/" element={<Dashboard />} />
          </Route>
          {/* fallback */}
          <Route path="*" element={<LoginPage />} />
        </Routes>
      </BrowserRouter>
      <Toaster richColors closeButton />
    </QueryClientProvider>
  );
}
