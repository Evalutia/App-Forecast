import React, { useEffect, useRef } from 'react';
import type { JobsQuery } from '../../jobs/types/jobs';
import TablaJobs from '../../jobs/components/TablaJobs';
import '../../../styles/dark-layout.css';

const ESTADOS = ['pendiente', 'ejecutando', 'exitoso', 'fallido', 'cancelado'];

export default function JobsPage() {
  const [query, setQuery] = React.useState<JobsQuery>({
    page: 1, pageSize: 20, tipo: '', estado: '', desde: '', hasta: '',
  });

  const filterRef = useRef<HTMLElement | null>(null);
  const tableRef  = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const els = [filterRef.current, tableRef.current].filter(Boolean) as HTMLElement[];
    const obs = new IntersectionObserver(
      entries => entries.forEach(e => { if (e.isIntersecting) { (e.target as HTMLElement).classList.add('visible'); obs.unobserve(e.target); } }),
      { threshold: 0.04 }
    );
    els.forEach(el => obs.observe(el));
    return () => obs.disconnect();
  }, []);

  const onChange = <K extends keyof JobsQuery>(k: K) => (v: JobsQuery[K]) =>
    setQuery(q => ({ ...q, [k]: v, page: 1 }));

  return (
    <div className="pg-page">

      <section className="pg-hero">
        <div className="pg-hero-grid" />
        <div className="pg-hero-glow" />
        <div className="pg-hero-content">
          <h1 className="pg-title">Ejecuciones</h1>
          <p className="pg-subtitle">Historial de jobs ETL y corridas de predicción.</p>
        </div>
      </section>

      <div className="pg-container pg-container--wide">

        <section className="pg-filter-card pg-reveal" ref={filterRef}>
          <div className="pg-filters-grid">
            <div className="pg-form-row">
              <label className="pg-label">Tipo de job</label>
              <input className="pg-input" placeholder="ej. forecast, etl…"
                value={query.tipo ?? ''} onChange={e => onChange('tipo')(e.target.value)} />
            </div>
            <div className="pg-form-row">
              <label className="pg-label">Estado</label>
              <select className="pg-select" value={query.estado ?? ''} onChange={e => onChange('estado')(e.target.value)}>
                <option value="">Todos</option>
                {ESTADOS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="pg-form-row">
              <label className="pg-label">Desde</label>
              <input type="date" className="pg-input"
                value={query.desde ?? ''} onChange={e => onChange('desde')(e.target.value)} />
            </div>
            <div className="pg-form-row">
              <label className="pg-label">Hasta</label>
              <input type="date" className="pg-input"
                value={query.hasta ?? ''} onChange={e => onChange('hasta')(e.target.value)} />
            </div>
          </div>
          <div className="pg-filter-actions">
            <button type="button" className="pg-btn" onClick={() => setQuery(q => ({ ...q }))}>Aplicar</button>
            <button type="button" className="pg-btn-ghost"
              onClick={() => setQuery({ page: 1, pageSize: 20, tipo: '', estado: '', desde: '', hasta: '' })}>
              Limpiar
            </button>
          </div>
        </section>

        <section className="pg-table-card pg-reveal" ref={tableRef}>
          <TablaJobs query={query} onQueryChange={setQuery} />
        </section>

      </div>
    </div>
  );
}
