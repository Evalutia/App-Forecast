import { BrowserRouter, Routes, Route } from 'react-router-dom';
import RequireAuth from './RequireAuth';
import LoginPage from '../features/auth/pages/LoginPage';
import UsersPage from '../features/users/pages/UsersPage';
import PrediccionesPage from '../features/predictions/pages/PrediccionesPage';
import LogoutButton from '../features/auth/components/LogoutButton';
import AdminUsersButton from '../features/auth/components/AdminUsersButton';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';

const queryClient = new QueryClient();

function Dashboard() {
  return (
    <div className="min-h-dvh bg-gradient-to-br from-emerald-950 via-emerald-900 to-emerald-950 px-6 py-6">
      {/* Header */}
      <div className="mx-auto flex max-w-5xl items-center justify-between">
        <span className="text-sm text-emerald-100/80">Evalutia</span>
        <div className="flex items-center gap-2">
          <AdminUsersButton />
          <LogoutButton />
        </div>
      </div>

      {/* Hero */}
      <div className="mx-auto mt-10 flex max-w-2xl flex-col items-center justify-center gap-6 text-center">
        <span className="rounded-full border border-white/10 bg-white/10 px-4 py-1 text-xs font-medium uppercase tracking-[0.3em] text-emerald-100">
          Panel principal
        </span>
        <h1 className="text-4xl font-semibold text-white sm:text-5xl">Bienvenido al portal Evalutia</h1>
        <p className="text-lg leading-relaxed text-emerald-100/90">
          Gestioná y visualizá tus métricas clave en un entorno claro, moderno y enfocado
          en lo que realmente importa.
        </p>

        {/* Botón "Ver predicciones" */}
        <div className="mt-4">
          <a
            href="/predicciones"
            className="rounded-lg bg-emerald-600/90 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600"
          >
            Ver predicciones
          </a>
        </div>
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
            <Route path="/usuarios" element={<UsersPage />} />
            <Route path="/predicciones" element={<PrediccionesPage />} /> 
          </Route>
          {/* fallback */}
          <Route path="*" element={<LoginPage />} />
        </Routes>
      </BrowserRouter>
      <Toaster richColors closeButton />
    </QueryClientProvider>
  );
}