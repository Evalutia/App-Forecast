import React from 'react';
import type { JobsQuery } from '../../jobs/types/jobs';
import TablaJobs from '../../jobs/components/TablaJobs';
import BackToDashboardButton from '../../users/components/BackToDashboardButton';
import ScrollToTopButton from '../../users/components/ScrollToTopButton';

const ESTADOS = ['pendiente','ejecutando','exitoso','fallido','cancelado'];

export default function JobsPage() {
  const [query, setQuery] = React.useState<JobsQuery>({
    page: 1, pageSize: 20, tipo: '', estado: '', desde: '', hasta: '',
  });

  const onChange = <K extends keyof JobsQuery>(k: K) => (v: JobsQuery[K]) =>
    setQuery((q) => ({ ...q, [k]: v, page: 1 }));

  return (
    <div className="predicciones-page">
      <div className="predicciones-header">
        <a href="/home" className="predicciones-brand">Evalutia</a>
        <div className="predicciones-actions">
          <BackToDashboardButton />
        </div>
      </div>

      <div style={{ padding: '1.5rem 1rem' }}>
        <div className="jobs-container">
          <header className="section-head">
            <h1 className="section-title">Jobs</h1>
            <p className="section-subtitle">Historial y estado de ejecuciones.</p>
          </header>

          {/* Filtros */}
          <section className="card filters-card jobs-filtros">
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

            <div className="filters-actions jobs-filtros-actions">
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
                onClick={() => setQuery({ page: 1, pageSize: 20, tipo: '', estado: '', desde: '', hasta: '' })}
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
      <ScrollToTopButton />
    </div>
  );
}
