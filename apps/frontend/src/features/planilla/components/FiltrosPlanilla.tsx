import { usePlanillaFiltros } from '../hooks/usePlanilla';

const ESTADOS_MES = [
  { value: '',               label: 'Todos los estados'  },
  { value: 'normal',         label: 'Normal'             },
  { value: 'quiebre_parcial',label: 'Quiebre parcial'    },
  { value: 'sin_stock',      label: 'Sin stock'          },
];

type Props = {
  marcaId:    number | undefined;
  generoId:   number | undefined;
  estadoMes:  string | undefined;
  onFilterChange: (updates: { marcaId?: number; generoId?: number; estadoMes?: string }) => void;
  onReset: () => void;
};

export default function FiltrosPlanilla({ marcaId, generoId, estadoMes, onFilterChange, onReset }: Props) {
  const { data: filtros, isLoading, isError } = usePlanillaFiltros();

  const cargando  = isLoading;
  const marcas    = filtros?.marcas  ?? [];
  const generos   = filtros?.generos ?? [];
  const sinMarca  = filtros?.articulosIncompletos.sinMarca  ?? 0;
  const sinGenero = filtros?.articulosIncompletos.sinGenero ?? 0;
  const hayIncompletos   = !isError && !isLoading && (sinMarca > 0 || sinGenero > 0);
  const hayFiltrosActivos = marcaId != null || generoId != null || (estadoMes != null && estadoMes !== '');

  return (
    <section className="pg-filter-card">
      <div className="pg-filters-grid">

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
