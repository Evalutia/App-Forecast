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

export default function PrediccionesPage() {
  const [sp, setSp] = useSearchParams();
  const jobId = useMemo(() => getInt(sp, 'jobId'), [sp]);

  const { data: byJob, isLoading: loadingByJob, isError: errorByJob } = usePrediccionesByJob(jobId);

  const clearJobId = () => {
    const next = new URLSearchParams(sp);
    next.delete('jobId');
    next.set('page', '1');
    setSp(next, { replace: true });
  };

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
                    {(byJob ?? []).map((p) => (
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
                    ))}
                  </tbody>
                </table>
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
