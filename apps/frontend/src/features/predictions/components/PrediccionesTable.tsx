import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { usePrediccionesSearch } from '../hooks/usePredicciones';
import type { PrediccionSearchParams } from '../types/predicciones';

type Props = {
  className?: string;
};

function getParam(sp: URLSearchParams, k: string) {
  const v = sp.get(k);
  return v && v.length ? v : undefined;
}
function getInt(sp: URLSearchParams, k: string, def: number) {
  const v = Number(sp.get(k));
  return Number.isFinite(v) && v > 0 ? v : def;
}

export default function PrediccionesTable({ className }: Props) {
  const [sp, setSp] = useSearchParams();

  const params: PrediccionSearchParams = useMemo(() => {
    return {
      sku: getParam(sp, 'sku'),
      modelo: getParam(sp, 'modelo'),
      desde: getParam(sp, 'desde'),
      hasta: getParam(sp, 'hasta'),
      page: getInt(sp, 'page', 1),
      pageSize: getInt(sp, 'pageSize', 20),
    };
  }, [sp]);

  const { data, isLoading, isError } = usePrediccionesSearch(params);
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 20;
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const setPage = (nextPage: number) => {
    const next = new URLSearchParams(sp);
    next.set('page', String(nextPage));
    setSp(next, { replace: true });
  };

  const setPageSize = (nextPageSize: number) => {
    const next = new URLSearchParams(sp);
    next.set('pageSize', String(nextPageSize));
    next.set('page', '1');
    setSp(next, { replace: true });
  };

  return (
    <div className={['rounded-xl border border-white/10 bg-white/5 p-4', className].filter(Boolean).join(' ')}>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">Historial de predicciones</h3>
        <div className="flex items-center gap-2 text-xs text-emerald-100/70">
          <span>Total: {total}</span>
          <span>·</span>
          <span>Página {page} de {totalPages}</span>
        </div>
      </div>

      {isLoading ? (
        <div className="text-emerald-100/80">Cargando…</div>
      ) : isError ? (
        <div className="rounded-lg border border-rose-400/20 bg-rose-400/10 p-3 text-rose-100">
          Error cargando el historial.
        </div>
      ) : (
        <>
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
                  <th className="px-2 py-2 text-left">Job</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10 text-emerald-100/90">
                {(data?.items ?? []).map((p) => (
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
                    <td className="px-2 py-2">
                      {typeof p.jobId === 'number' ? (
                        <Link
                          to={`/predicciones?jobId=${p.jobId}&page=1`}
                          className="text-emerald-200 hover:underline"
                          title="Ver predicciones de este job"
                        >
                          #{p.jobId}
                        </Link>
                      ) : (
                        <span className="text-emerald-100/60">—</span>
                      )}
                    </td>
                  </tr>
                ))}
                {(data?.items?.length ?? 0) === 0 && (
                  <tr>
                    <td className="px-2 py-6 text-center text-emerald-100/70" colSpan={10}>
                      No se encontraron predicciones para los filtros seleccionados.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Paginación simple local (podés reemplazar por tu Pagination reusado si ya lo tenés) */}
          <div className="mt-3 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-emerald-100/80">
              <span>Filas por página:</span>
              <select
                className="rounded border border-white/15 bg-white/10 px-2 py-1 text-emerald-100/90 outline-none"
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value))}
              >
                {[10, 20, 50, 100].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage(1)}
                disabled={page <= 1}
                className="rounded border border-white/15 px-2 py-1 text-sm text-emerald-100/80 disabled:opacity-40"
              >
                « Primero
              </button>
              <button
                type="button"
                onClick={() => setPage(page - 1)}
                disabled={page <= 1}
                className="rounded border border-white/15 px-2 py-1 text-sm text-emerald-100/80 disabled:opacity-40"
              >
                ‹ Anterior
              </button>
              <button
                type="button"
                onClick={() => setPage(page + 1)}
                disabled={page >= totalPages}
                className="rounded border border-white/15 px-2 py-1 text-sm text-emerald-100/80 disabled:opacity-40"
              >
                Siguiente ›
              </button>
              <button
                type="button"
                onClick={() => setPage(totalPages)}
                disabled={page >= totalPages}
                className="rounded border border-white/15 px-2 py-1 text-sm text-emerald-100/80 disabled:opacity-40"
              >
                Último »
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
