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
    <div className="home-page">
      {/* Header */}
      <div className="home-header">
        {/* Evalutia ahora es link a /home */}
        <a href="/home" className="home-brand">Evalutia</a>
        <div className="home-actions">
          <AdminUsersButton />
          <LogoutButton />
        </div>
      </div>

      {/* Hero */}
      <div className="home-hero">
        <h1 className="home-title">Bienvenido al portal Evalutia</h1>
        <p className="home-subtitle">
          Gestioná y visualizá tus métricas clave en un entorno claro, moderno y enfocado
          en lo que realmente importa.
        </p>

        {/* CTA */}
        <div>
          <a href="/predicciones" className="btn">
            Ver mis predicciones
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
            {/* alias /home apunta al mismo Dashboard */}
            <Route path="/home" element={<Dashboard />} />
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
