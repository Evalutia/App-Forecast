import React from 'react';
import type { JobsQuery } from '../../jobs/types/jobs';
import TablaJobs from '../../jobs/components/TablaJobs';

const ESTADOS = ['pendiente','ejecutando','exitoso','fallido','cancelado'];

export default function JobsPage() {
  const [query, setQuery] = React.useState<JobsQuery>({
    page: 1, pageSize: 50, tipo: '', estado: '', desde: '', hasta: '',
  });

  const onChange = <K extends keyof JobsQuery>(k: K) => (v: JobsQuery[K]) =>
    setQuery((q) => ({ ...q, [k]: v, page: 1 }));

  return (
    <>
      {/* Topbar idéntica a Home/Sales */}
      <div className="jobs-topbar-wide">
        <div className="home-header">
          <a href="/home" className="home-brand">EVALUTIA</a>
          <div className="home-actions">
            {/* Botón igual al de Sales */}
            <a href="/home" className="btn btn--sm">← Volver al dashboard</a>
          </div>
        </div>
      </div>

      <div className="jobs-page">
        <div className="jobs-container">
          <header className="section-head">
            <h1 className="section-title">Jobs</h1>
            <p className="section-subtitle">Historial y estado de ejecuciones.</p>
          </header>

          {/* Filtros */}
          <section className="card filters-card">
            <div className="filters-grid">
              <div className="form-row">
                <label className="label">Tipo de job</label>
                <input
                  className="input"
                  placeholder="p.ej. forecast, etl..."
                  value={query.tipo ?? ''}
                  onChange={(e) => onChange('tipo')(e.target.value)}
                />
              </div>

              <div className="form-row">
                <label className="label">Estado</label>
                <select
                  className="select"
                  value={query.estado ?? ''}
                  onChange={(e) => onChange('estado')(e.target.value)}
                >
                  <option value="">Todos</option>
                  {ESTADOS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>

              <div className="form-row">
                <label className="label">Desde</label>
                <input
                  type="date"
                  className="input"
                  value={query.desde ?? ''}
                  onChange={(e) => onChange('desde')(e.target.value)}
                />
              </div>

              <div className="form-row">
                <label className="label">Hasta</label>
                <input
                  type="date"
                  className="input"
                  value={query.hasta ?? ''}
                  onChange={(e) => onChange('hasta')(e.target.value)}
                />
              </div>
            </div>

            {/* Acciones abajo (fuera del grid), igual que Ventas */}
            <div className="filters-actions">
              <button
                type="button"
                className="button"
                onClick={() => setQuery((q) => ({ ...q }))}
              >
                Aplicar filtros
              </button>
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setQuery({ page: 1, pageSize: 50, tipo: '', estado: '', desde: '', hasta: '' })}
              >
                Limpiar
              </button>
            </div>
          </section>


          <section style={{ marginTop: '1rem', width: '100%' }}>
            <TablaJobs query={query} onQueryChange={setQuery} />
          </section>
        </div>
      </div>
    </>
  );
}
