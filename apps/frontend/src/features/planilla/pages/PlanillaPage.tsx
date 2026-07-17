import { useMemo, useState } from 'react';
import FiltrosPlanilla from '../components/FiltrosPlanilla';
import PlanillaTable from '../components/PlanillaTable';
import { usePlanillaSugerencias } from '../hooks/usePlanilla';
import type { PlanillaSugerenciaDto, PlanillaVentasParams } from '../types/planilla';
import '../../../styles/dark-layout.css';
import '../../../styles/planilla.css';

const DEFAULT_PAGE_SIZE = 50;

export default function PlanillaPage() {
  const [page, setPage]       = useState(1);
  const [pageSize]            = useState(DEFAULT_PAGE_SIZE);
  const [marcaId, setMarcaId] = useState<number | undefined>();
  const [generoId, setGeneroId] = useState<number | undefined>();
  const [grupoId, setGrupoId] = useState<number | undefined>();
  const [estadoMes, setEstadoMes] = useState<string | undefined>();

  const params: PlanillaVentasParams = { page, pageSize, marcaId, generoId, grupoId, estadoMes };

  const { data: sugerenciasData, isLoading: sugerenciasLoading } = usePlanillaSugerencias();
  const sugerencias = useMemo<Map<string, PlanillaSugerenciaDto>>(
    () => new Map((sugerenciasData ?? []).map(s => [s.sku, s])),
    [sugerenciasData]
  );

  const handlePageChange = (nextPage: number) => setPage(nextPage);

  const handleFilterChange = (updates: Partial<{ marcaId?: number; generoId?: number; grupoId?: number; estadoMes?: string }>) => {
    if ('marcaId'   in updates) setMarcaId(updates.marcaId);
    if ('generoId'  in updates) setGeneroId(updates.generoId);
    if ('grupoId'   in updates) {
      setGrupoId(updates.grupoId);
      // Cambiar de grupo invalida la marca/género seleccionados: pueden no existir en el nuevo grupo
      setMarcaId(undefined);
      setGeneroId(undefined);
    }
    if ('estadoMes' in updates) setEstadoMes(updates.estadoMes);
    setPage(1);
  };

  const handleReset = () => {
    setMarcaId(undefined);
    setGeneroId(undefined);
    setGrupoId(undefined);
    setEstadoMes(undefined);
    setPage(1);
  };

  return (
    <div className="pg-page">

      <section className="pg-hero">
        <div className="pg-hero-grid" />
        <div className="pg-hero-glow" />
        <div className="pg-hero-content">
          <h1 className="pg-title">Planilla de Reposición</h1>
          <p className="pg-subtitle">
            Rotación histórica y métricas de reposición por artículo.
          </p>
        </div>
      </section>

      <div className="pg-container pg-container--wide">
        <FiltrosPlanilla
          marcaId={marcaId}
          generoId={generoId}
          grupoId={grupoId}
          estadoMes={estadoMes}
          onFilterChange={handleFilterChange}
          onReset={handleReset}
        />

        <PlanillaTable
          params={params}
          onPageChange={handlePageChange}
          sugerencias={sugerencias}
          sugerenciasLoading={sugerenciasLoading}
        />
      </div>

    </div>
  );
}
