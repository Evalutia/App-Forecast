import React from 'react';
import { Link } from 'react-router-dom';
import { useJobs, usePrefetchNextJobsPage } from '../hooks/useJobs';
import type { JobsQuery, JobItem } from '../types/jobs';

function formatDateTime(iso?: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const dd = d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', year: 'numeric' });
  const hh = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  return `${dd} ${hh}`;
}

function EstadoBadge({ estado }: { estado: string }) {
  const k = (estado || 'desconocido').toLowerCase();
  const map: Record<string, string> = {
    pendiente: 'badge badge-pendiente',
    ejecutando: 'badge badge-ejecutando',
    exitoso: 'badge badge-exitoso',
    fallido: 'badge badge-fallido',
    cancelado: 'badge badge-cancelado',
  };
  const cls = map[k] ?? 'badge badge-default';
  return <span className={cls}>{estado || 'desconocido'}</span>;
}

export default function TablaJobs({ query, onQueryChange }: { query: JobsQuery; onQueryChange: (q: JobsQuery) => void; }) {
  const { data, isLoading, isFetching } = useJobs(query);
  const prefetchNext = usePrefetchNextJobsPage(query);

  const items = data?.items ?? [];
  const page = data?.page ?? query.page ?? 1;
  const pageSize = data?.pageSize ?? query.pageSize ?? 50;
  const total = data?.total ?? 0;

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const canPrev = page > 1;
  const canNext = page < totalPages;

  React.useEffect(() => { prefetchNext(items.length).catch(() => {}); }, [items.length]);

  const goPage = (p: number) => onQueryChange({ ...query, page: Math.min(Math.max(1, p), totalPages) });

  return (
    <section className="card table-card">
      <div style={{ marginBottom: '.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="muted">{isFetching ? 'Actualizando…' : 'Historial de jobs'}</div>
        <div className="muted">Total: <strong>{total}</strong></div>
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Tipo</th>
              <th>Estado</th>
              <th>Inicio</th>
              <th>Fin</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && items.length === 0 ? (
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i}>
                  <td><span className="skeleton skel-12" /></td>
                  <td><span className="skeleton skel-24" /></td>
                  <td><span className="skeleton skel-20" /></td>
                  <td><span className="skeleton skel-24" /></td>
                  <td><span className="skeleton skel-24" /></td>
                  <td><span className="skeleton skel-20" /></td>
                </tr>
              ))
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={6} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>
                  No hay resultados para los filtros aplicados.
                </td>
              </tr>
            ) : (
              items.map((j: JobItem) => (
                <tr key={j.id}>
                  <td className="mono">#{j.id}</td>
                  <td>{j.tipoJob}</td>
                  <td><EstadoBadge estado={j.estado} /></td>
                  <td>{formatDateTime(j.fechaInicio)}</td>
                  <td>{formatDateTime(j.fechaFin)}</td>
                  <td>
                    <div style={{ display:'flex', justifyContent: 'center', gap:'.8rem' }}>
                      <Link to={`/jobs/${j.id}`}>Detalle</Link>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="pager">
        <div>Página {page} de {totalPages}</div>
        <div className="pager-buttons">
          <button className="pager-btn" disabled={!canPrev} onClick={() => goPage(page - 1)}>Anterior</button>
          <button className="pager-btn" disabled={!canNext} onClick={() => goPage(page + 1)}>Siguiente</button>
        </div>
      </div>
      <div style={{ marginTop: '.5rem' }} className="muted">
        Filas por página:&nbsp;
        <select
          value={pageSize}
          onChange={(e) => onQueryChange({ ...query, pageSize: Number(e.target.value), page: 1 })}
        >
          {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      </div>
    </section>
  );
}
