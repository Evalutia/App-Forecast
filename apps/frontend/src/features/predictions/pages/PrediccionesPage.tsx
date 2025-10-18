// apps/frontend/src/apps/predicciones/pages/PrediccionesPage.tsx
import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import BackToDashboardButton from '../../users/components/BackToDashboardButton';
import PrediccionesFilters from '../components/PrediccionesFilters';
import UltimasPredicciones from '../components/UltimasPredicciones';
import PrediccionesTable from '../components/PrediccionesTable';
import DatosExtra from '../components/DatosExtra';
import { usePrediccionesByJob } from '../hooks/usePredicciones';

function getInt(sp: URLSearchParams, k: string): number | null {
  const raw = sp.get(k);
  if (raw === null || raw === '') return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}
function getIntOr(sp: URLSearchParams, k: string, def: number): number {
  const n = Number(sp.get(k));
  return Number.isFinite(n) && n > 0 ? n : def;
}

export default function PrediccionesPage() {
  const [sp, setSp] = useSearchParams();
  const jobId = useMemo(() => getInt(sp, 'jobId'), [sp]);

  const { data: byJob, isLoading: loadingByJob, isError: errorByJob } = usePrediccionesByJob(jobId);

  // ---- estado de paginado (solo cliente) para la tabla del Job ----
  const jobPage = getIntOr(sp, 'jobPage', 1);
  const jobPageSize = getIntOr(sp, 'jobPageSize', 20);
  const setJobPage = (p: number) => {
    const next = new URLSearchParams(sp);
    next.set('jobPage', String(p));
    setSp(next, { replace: true });
  };
  const setJobPageSize = (s: number) => {
    const next = new URLSearchParams(sp);
    next.set('jobPageSize', String(s));
    next.set('jobPage', '1');
    setSp(next, { replace: true });
  };

  const clearJobId = () => {
    const next = new URLSearchParams(sp);
    next.delete('jobId');
    next.delete('jobPage');
    next.delete('jobPageSize');
    next.set('page', '1'); // mantener coherencia con la tabla general
    setSp(next, { replace: true });
  };

  // --- cálculo de paginado para el Job ---
  const itemsJob = byJob ?? [];
  const totalJob = itemsJob.length;
  const totalPagesJob = Math.max(1, Math.ceil(totalJob / jobPageSize));
  const startJob = (jobPage - 1) * jobPageSize;
  const endJob = Math.min(startJob + jobPageSize, totalJob);
  const pageItemsJob = itemsJob.slice(startJob, endJob);

  return (
    <div className="predicciones-page">
      {/* ===== Header (clon 1:1 de Ventas) ===== */}
      <div className="predicciones-header">
        <a href="/home" className="predicciones-brand">Evalutia</a>

        <div className="predicciones-actions">
          <BackToDashboardButton />
        </div>
      </div>

      {/* ===== Contenido ===== */}
      <div className="predicciones-container">
        <header className="section-head">
          <h1 className="section-title">Predicciones</h1>
          <p className="section-subtitle">
            Consultá las últimas corridas, buscá por SKU/fechas y explorá los datos extra.
          </p>
        </header>

        {/* Sección: Últimas corridas */}
        <h2 className="subsection-title">Últimas predicciones (del último job)</h2>
        <UltimasPredicciones />

        {/* Sección: Búsqueda por SKU/fechas */}
        <h2 className="subsection-title">Búsqueda por SKU/fechas</h2>
        <PrediccionesFilters />

        {/* Historial paginado (respeta filtros de la URL) */}
        <PrediccionesTable />

        {/* Si hay jobId en la URL, mostramos bloque especial */}
        {typeof jobId === 'number' && (
          <>
            <h2 className="subsection-title">Predicciones del Job #{jobId}</h2>

            <section className="card table-card predicciones-job">
              <div style={{ marginBottom: '.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div className="muted">
                  {loadingByJob ? 'Cargando…' : (errorByJob ? 'Error al cargar' : 'Resultados del job')}
                </div>
                <div className="muted">Total: <strong>{totalJob}</strong></div>
              </div>

              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>SKU</th>
                      <th>Fecha</th>
                      <th style={{ textAlign:'right' }}>Cantidad</th>
                      <th>Modelo</th>
                      <th>Versión</th>
                      <th style={{ textAlign:'right' }}>h</th>
                      <th style={{ textAlign:'right' }}>R²</th>
                      <th style={{ textAlign:'right' }}>RMSE</th>
                      <th>Generación</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loadingByJob && itemsJob.length === 0 ? (
                      Array.from({ length: 8 }).map((_, i) => (
                        <tr key={i}>
                          <td><span className="skeleton skel-28" /></td>
                          <td><span className="skeleton skel-24" /></td>
                          <td><span className="skeleton skel-12" /></td>
                          <td><span className="skeleton skel-24" /></td>
                          <td><span className="skeleton skel-20" /></td>
                          <td><span className="skeleton skel-10" /></td>
                          <td><span className="skeleton skel-12" /></td>
                          <td><span className="skeleton skel-12" /></td>
                          <td><span className="skeleton skel-24" /></td>
                        </tr>
                      ))
                    ) : pageItemsJob.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>
                          {errorByJob ? 'No se pudo cargar este job.' : 'Sin resultados para este job.'}
                        </td>
                      </tr>
                    ) : (
                      pageItemsJob.map((p) => (
                        <tr key={p.id}>
                          <td className="mono">{p.sku}</td>
                          <td>{p.fechaPredicha}</td>
                          <td style={{ textAlign:'right' }}>{p.cantidadPredicha}</td>
                          <td>{p.modelo}</td>
                          <td>{p.versionModelo}</td>
                          <td style={{ textAlign:'right' }}>{p.horizonte}</td>
                          <td style={{ textAlign:'right' }}>{p.r2 ?? '-'}</td>
                          <td style={{ textAlign:'right' }}>{p.rmse ?? '-'}</td>
                          <td>{p.tsGeneracion}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Paginador */}
              <div className="pager">
                <div>
                  Página {jobPage} de {totalPagesJob}
                  <span className="muted"> &nbsp;·&nbsp; Mostrando {startJob + 1}–{endJob}</span>
                </div>
                <div className="pager-buttons">
                  <button className="pager-btn" disabled={jobPage <= 1} onClick={() => setJobPage(jobPage - 1)}>Anterior</button>
                  <button className="pager-btn" disabled={jobPage >= totalPagesJob} onClick={() => setJobPage(jobPage + 1)}>Siguiente</button>
                </div>
              </div>

              {/* selector de tamaño (opcional) */}
              <div style={{ marginTop: '.5rem' }} className="muted">
                Filas por página:&nbsp;
                <select value={jobPageSize} onChange={(e) => setJobPageSize(Number(e.target.value))}>
                  {[10,20,50,100].map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </div>

              <div style={{ marginTop: '.75rem', display:'flex', justifyContent:'flex-end' }}>
                <button
                  type="button"
                  onClick={clearJobId}
                  className="pager-btn"
                  title="Limpiar Job"
                >
                  Limpiar Job
                </button>
              </div>
            </section>
          </>
        )}

        {/* Sección: Datos extra */}
        <h2 className="subsection-title">Datos extra (gráficas)</h2>
        <DatosExtra />
      </div>
    </div>
  );
}
