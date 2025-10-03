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

        {/* Últimas predicciones */}
        <UltimasPredicciones />

        {/* Filtros */}
        <PrediccionesFilters />

        {/* Historial paginado (respeta filtros de la URL) */}
        <PrediccionesTable />

        {/* Si hay jobId en la URL, mostramos bloque especial */}
        {typeof jobId === 'number' && (
          <div className="predicciones-job rounded-xl border border-white/10 bg-white/5 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">
                Predicciones del Job #{jobId}
              </h3>
              <button
                type="button"
                onClick={clearJobId}
                className="rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-emerald-100/90 hover:bg-white/10"
              >
                Limpiar Job
              </button>
            </div>

            {loadingByJob ? (
              <div className="text-emerald-100/80">Cargando…</div>
            ) : errorByJob ? (
              <div className="rounded-lg border border-rose-400/20 bg-rose-400/10 p-3 text-rose-100">
                Error cargando las predicciones de este job.
              </div>
            ) : (byJob?.length ?? 0) === 0 ? (
              <div className="text-emerald-100/80">Sin resultados para este job.</div>
            ) : (
              <div className="overflow-x-auto -mx-2 sm:mx-0">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-emerald-100/70">
                      <th className="px-2 py-2 text-left">SKU</th>
                      <th className="px-2 py-2 text-left">Fecha</th>
                      <th className="px-2 py-2 text-right">Cantidad</th>
                      <th className="px-2 py-2 text-left">Modelo</th>
                      <th className="px-2 py-2 text-left">Versión</th>
                      <th className="px-2 py-2 text-right">h</th>
                      <th className="px-2 py-2 text-right">R²</th>
                      <th className="px-2 py-2 text-right">RMSE</th>
                      <th className="px-2 py-2 text-left">Generación</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/10 text-emerald-100/90">
                    {(byJob ?? []).map((p) => (
                      <tr key={p.id}>
                        <td className="px-2 py-2">
                          <span className="inline-flex rounded bg-white/10 px-2 py-0.5 text-xs">{p.sku}</span>
                        </td>
                        <td className="px-2 py-2">{p.fechaPredicha}</td>
                        <td className="px-2 py-2 text-right">{p.cantidadPredicha}</td>
                        <td className="px-2 py-2">{p.modelo}</td>
                        <td className="px-2 py-2">{p.versionModelo}</td>
                        <td className="px-2 py-2 text-right">{p.horizonte}</td>
                        <td className="px-2 py-2 text-right">{p.r2 ?? '-'}</td>
                        <td className="px-2 py-2 text-right">{p.rmse ?? '-'}</td>
                        <td className="px-2 py-2">{p.tsGeneracion}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Datos extra: gráficas */}
        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <DatosExtra />
        </div>
      </div>
    </div>
  );
}
