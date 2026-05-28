import { BrowserRouter, Routes, Route } from 'react-router-dom';
import RequireAuth from './RequireAuth';
import RequireAdmin from './RequireAdmin';
import LoginPage from '../features/auth/pages/LoginPage';
import UsersPage from '../features/users/pages/UsersPage';
import PrediccionesPage from '../features/predictions/pages/PrediccionesPage';
import VentasPage from "../features/sales/pages/VentasPage";
import JobsPage from '../features/jobs/pages/JobsPage';
import ArticulosPage from '../features/articles/pages/ArticulosPage';
import VentasMensualesPage from '../features/salesmonthly/pages/VentasMensualesPage';
import StockDiarioPage from '../features/stock/pages/StockDiarioPage';
import ResultadosPage from '../features/resultados/pages/ResultadosPage';
import PlanillaPage from '../features/planilla/pages/PlanillaPage';
import JobDetailPage from '../features/jobs/pages/JobDetailPage';
import DashboardPage from '../features/home/pages/DashboardPage';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';

const queryClient = new QueryClient();

export default function AppRoutes() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* públicas */}
          <Route path="/login" element={<LoginPage />} />
          {/* privadas */}
          <Route element={<RequireAuth />}>
            <Route path="/"     element={<DashboardPage />} />
            <Route path="/home" element={<DashboardPage />} />
            <Route path="/predicciones" element={<PrediccionesPage />} />
            <Route path="/articulos" element={<ArticulosPage />} />
            <Route path="/ventas-mensuales" element={<VentasMensualesPage />} />
            <Route path="/stock-diario" element={<StockDiarioPage />} />
            <Route path="/resultados" element={<ResultadosPage />} />
            <Route path="/planilla" element={<PlanillaPage />} />
            {/* Solo administradores */}
            <Route element={<RequireAdmin />}>
              <Route path="/usuarios" element={<UsersPage />} />
              <Route path="/ventas" element={<VentasPage />} />
              <Route path="/jobs" element={<JobsPage />} />
              <Route path="/jobs/:id" element={<JobDetailPage />} />
            </Route>
          </Route>
          {/* fallback */}
          <Route path="*" element={<LoginPage />} />
        </Routes>
      </BrowserRouter>
      <Toaster richColors closeButton theme="dark" position="top-right" />
    </QueryClientProvider>
  );
}
