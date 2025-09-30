import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import BackToDashboardButton from '../../users/components/BackToDashboardButton';
import PrediccionesFilters from '../components/PrediccionesFilters';
import UltimasPredicciones from '../components/UltimasPredicciones';
import PrediccionesTable from '../components/PrediccionesTable';
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
    <div className="min-h-dvh bg-gradient-to-br from-emerald-950 via-emerald-900 to-emerald-950 px-6 py-6">
      {/* Header */}
      <div className="mx-auto flex max-w-5xl items-center justify-between">
        <span className="text-sm text-emerald-100/80">Evalutia</span>
        <BackToDashboardButton />
      </div>

      {/* Título */}
      <div className="mx-auto mt-8 max-w-5xl">
        <h1 className="text-3xl font-semibold text-white">Predicciones</h1>
        <p className="mt-1 text-emerald-100/80">
          Consultá las últimas corridas, buscá por SKU/fechas y explorá los datos extra.
        </p>
      </div>

      <div className="mx-auto mt-6 grid max-w-5xl gap-6">
        {/* Últimas predicciones */}
        <UltimasPredicciones />

        {/* Filtros */}
        <PrediccionesFilters />

        {/* Historial paginado (respeta filtros de la URL) */}
        <PrediccionesTable />

        {/* Si hay jobId en la URL, mostramos bloque especial */}
        {typeof jobId === 'number' && (
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
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

        {/* Datos extra: placeholder para las gráficas (lo integramos en el próximo paso) */}
        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <h3 className="text-lg font-semibold text-white">Datos extra (gráficas)</h3>
          <p className="mt-1 text-emerald-100/80">
            Seleccioná un SKU en el historial para ver su serie histórica vs. predicción.
          </p>
          {/* Próximo paso: gráfico con react-chartjs-2 y selector de SKU */}
        </div>
      </div>
    </div>
  );
}
