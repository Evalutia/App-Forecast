import { usePlanillaFiltros } from '../hooks/usePlanilla';

const ESTADOS_MES = [
  { value: '',               label: 'Todos los estados'  },
  { value: 'normal',         label: 'Normal'             },
  { value: 'quiebre_parcial',label: 'Quiebre parcial'    },
  { value: 'sin_stock',      label: 'Sin stock'          },
];

// Criterio del mes vigente (el mas reciente de cada articulo), no "en algun
// momento del año": a diferencia de estadoMes (un quiebre puntual importa
// aunque haya sido hace meses), criterioFrecuencia depende de cuantos
// tickets tuvo CADA mes -- "al menos un mes" haria que casi cualquier SKU
// no-alta-frecuencia pasara el filtro. Lo que importa es que criterio
// respalda el numero que se ve HOY (mismo mes de referencia/"esRef" que ya
// resalta PlanillaTable.tsx en itálica).
const CRITERIOS_FRECUENCIA = [
  { value: '',                 label: 'Todos los criterios'          },
  { value: 'historico',        label: 'Histórico (≤2 tickets)'       },
  { value: 'promedio',         label: 'Promedio (3-4 tickets)'       },
  { value: 'real_extrapolado', label: 'Real / Extrapolado (≥5 tickets)' },
];

type Props = {
  marcaId:    number | undefined;
  generoId:   number | undefined;
  grupoId:    number | undefined;
  estadoMes:  string | undefined;
  criterioFrecuencia: string | undefined;
  onFilterChange: (updates: { marcaId?: number; generoId?: number; grupoId?: number; estadoMes?: string; criterioFrecuencia?: string }) => void;
  onReset: () => void;
};

export default function FiltrosPlanilla({ marcaId, generoId, grupoId, estadoMes, criterioFrecuencia, onFilterChange, onReset }: Props) {
  const { data: filtros, isLoading, isError } = usePlanillaFiltros(grupoId);

  const cargando  = isLoading;
  const marcas    = filtros?.marcas  ?? [];
  const generos   = filtros?.generos ?? [];
  const grupos    = filtros?.grupos  ?? [];
  const sinMarca  = filtros?.articulosIncompletos.sinMarca  ?? 0;
  const sinGenero = filtros?.articulosIncompletos.sinGenero ?? 0;
  const hayIncompletos   = !isError && !isLoading && (sinMarca > 0 || sinGenero > 0);
  const hayFiltrosActivos = marcaId != null || generoId != null || grupoId != null
      || (estadoMes != null && estadoMes !== '')
      || (criterioFrecuencia != null && criterioFrecuencia !== '');

  return (
    <section className="pg-filter-card">
      <div className="pg-filters-grid">

        <div className="pg-form-row">
          <label className="pg-label">Grupo</label>
          <select
            className="pg-select"
            disabled={cargando}
            value={grupoId ?? ''}
            onChange={e => onFilterChange({ grupoId: e.target.value ? Number(e.target.value) : undefined })}
          >
            <option value="">{cargando ? 'Cargando…' : 'Todos los grupos'}</option>
            {grupos.map(g => <option key={g.id} value={g.id}>{g.nombre}</option>)}
          </select>
        </div>

        <div className="pg-form-row">
          <label className="pg-label">Marca</label>
          <select
            className="pg-select"
            disabled={cargando}
            value={marcaId ?? ''}
            onChange={e => onFilterChange({ marcaId: e.target.value ? Number(e.target.value) : undefined })}
          >
            <option value="">{cargando ? 'Cargando…' : 'Todas las marcas'}</option>
            {marcas.map(m => <option key={m.id} value={m.id}>{m.nombre}</option>)}
          </select>
        </div>

        <div className="pg-form-row">
          <label className="pg-label">Género</label>
          <select
            className="pg-select"
            disabled={cargando}
            value={generoId ?? ''}
            onChange={e => onFilterChange({ generoId: e.target.value ? Number(e.target.value) : undefined })}
          >
            <option value="">{cargando ? 'Cargando…' : 'Todos los géneros'}</option>
            {generos.map(g => <option key={g.id} value={g.id}>{g.nombre}</option>)}
          </select>
        </div>

        <div className="pg-form-row">
          <label className="pg-label">Estado de stock</label>
          <select
            className="pg-select"
            value={estadoMes ?? ''}
            onChange={e => onFilterChange({ estadoMes: e.target.value || undefined })}
          >
            {ESTADOS_MES.map(({ value, label }) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>

        <div className="pg-form-row">
          <label className="pg-label">Criterio de frecuencia (mes vigente)</label>
          <select
            className="pg-select"
            value={criterioFrecuencia ?? ''}
            onChange={e => onFilterChange({ criterioFrecuencia: e.target.value || undefined })}
          >
            {CRITERIOS_FRECUENCIA.map(({ value, label }) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>

      </div>

      <div className="pg-filter-actions">
        <button
          type="button"
          className="pg-btn-ghost"
          onClick={onReset}
          disabled={!hayFiltrosActivos}
        >
          Limpiar filtros
        </button>
      </div>

      {hayIncompletos && (
        <div style={{ width: '100%', marginTop: '4px' }}>
          <p className="planilla-aviso-incompletos">
            ⚠{' '}
            {sinMarca  > 0 && `${sinMarca} artículo${sinMarca  > 1 ? 's' : ''} sin marca`}
            {sinMarca  > 0 && sinGenero > 0 && ' · '}
            {sinGenero > 0 && `${sinGenero} sin género`}
            {' '}— datos incompletos en el SOAP, no aparecen en los filtros.
          </p>
        </div>
      )}
    </section>
  );
}
