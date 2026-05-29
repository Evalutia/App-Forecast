import { useState } from 'react';
import BackToDashboardButton from '../../users/components/BackToDashboardButton';
import ScrollToTopButton from '../../users/components/ScrollToTopButton';
import PlanillaTable from '../components/PlanillaTable';
import type { PlanillaVentasParams } from '../types/planilla';

const DEFAULT_PAGE_SIZE = 50;

export default function PlanillaPage() {
  const [page, setPage] = useState(1);
  const [pageSize] = useState(DEFAULT_PAGE_SIZE);
  const [marcaId, setMarcaId] = useState<number | undefined>();
  const [generoId, setGeneroId] = useState<number | undefined>();
  const [estadoMes, setEstadoMes] = useState<string | undefined>();

  const params: PlanillaVentasParams = { page, pageSize, marcaId, generoId, estadoMes };

  const handlePageChange = (nextPage: number) => setPage(nextPage);

  const handleFilterChange = (updates: Partial<{ marcaId?: number; generoId?: number; estadoMes?: string }>) => {
    if ('marcaId' in updates) setMarcaId(updates.marcaId);
    if ('generoId' in updates) setGeneroId(updates.generoId);
    if ('estadoMes' in updates) setEstadoMes(updates.estadoMes);
    setPage(1);
  };

  const handleReset = () => {
    setMarcaId(undefined);
    setGeneroId(undefined);
    setEstadoMes(undefined);
    setPage(1);
  };

  return (
    <div className="planilla-page">
      <div className="planilla-header">
        <a href="/home" className="planilla-brand">Evalutia</a>
        <div className="planilla-actions">
          <BackToDashboardButton />
        </div>
      </div>

      <div className="planilla-container">
        <header className="section-head">
          <h1 className="section-title">Planilla de Reposición</h1>
          <p className="section-subtitle">
            Rotación histórica y métricas de reposición por artículo.
          </p>
        </header>

        {/* Filtros — issues #12 y #13 */}
        <section className="card filters-card planilla-filtros">
          <div className="planilla-filtros-placeholder">
            <span className="skeleton skel-120" />
            <span className="skeleton skel-120" />
          </div>
        </section>

        <PlanillaTable
          params={params}
          onPageChange={handlePageChange}
        />
      </div>

      <ScrollToTopButton />
    </div>
  );
}
