import { BrowserRouter, Routes, Route } from 'react-router-dom';
import RequireAuth from './RequireAuth';
import LoginPage from '../features/auth/pages/LoginPage';
import UsersPage from '../features/users/pages/UsersPage';
import PrediccionesPage from '../features/predictions/pages/PrediccionesPage';
import VentasPage from "../features/sales/pages/VentasPage";
import JobsPage from '../features/jobs/pages/JobsPage';
import JobDetailPage from '../features/jobs/pages/JobDetailPage';
import LogoutButton from '../features/auth/components/LogoutButton';
import AdminUsersButton from '../features/auth/components/AdminUsersButton';
import { useAuthUser } from '../features/auth/hooks/useAuthUser';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';

const queryClient = new QueryClient();

function Dashboard() {
  const { user } = useAuthUser();

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
        <h1 className="home-title">Tu negocio, gestionado con inteligencia.</h1>
        <p className="home-subtitle">
          Visualizá métricas clave, obtené predicciones confiables y optimizá la eficiencia de tu empresa en un solo lugar.
        </p>

        {/* CTA */}
        <div>
          <a href="/predicciones" className="btn">
            Ver mis predicciones
          </a>
        </div>
        <div>
          <a href="/ventas" className="btn">
            Ver las ventas cargadas
          </a>
        </div>
        {user && user.role === 'administrador' && (
          <div>
            <a href="/jobs" className="btn">
              Ver historial de ejecuciones 
            </a>
          </div>
        )}
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
            <Route path="/ventas" element={<VentasPage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/jobs/:id" element={<JobDetailPage />} />
          </Route>
          {/* fallback */}
          <Route path="*" element={<LoginPage />} />
        </Routes>
      </BrowserRouter>
      <Toaster richColors closeButton />
    </QueryClientProvider>
  );
}
