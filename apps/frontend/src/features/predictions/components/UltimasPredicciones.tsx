import { Link, useSearchParams } from 'react-router-dom';
import { useUltimasPredicciones } from '../hooks/usePredicciones';

export default function UltimasPredicciones() {
  const { data, isLoading, isError } = useUltimasPredicciones();
  const [, setSp] = useSearchParams();

  const goToHistorialConSku = (sku: string) => {
    const next = new URLSearchParams();
    next.set('sku', sku);
    next.set('page', '1');
    setSp(next);
  };

  if (isLoading) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-emerald-100/80">
        Cargando últimas predicciones…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-rose-400/20 bg-rose-400/10 p-4 text-rose-100">
        Ocurrió un error al cargar las últimas predicciones.
      </div>
    );
  }

  const items = data ?? [];

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">Últimas predicciones</h3>
        <span className="text-xs text-emerald-100/70">{items.length} ítems</span>
      </div>

      {items.length === 0 ? (
        <p className="text-emerald-100/80">Sin datos por el momento.</p>
      ) : (
        <ul className="divide-y divide-white/10">
          {items.map((p) => (
            <li key={p.id ?? `${p.sku}-${p.fechaPredicha}-${p.modelo}-${p.horizonte}-${p.versionModelo ?? ''}-${p.tsGeneracion ?? ''}`} 
            className="py-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center rounded bg-white/10 px-2 py-0.5 text-xs text-emerald-100">
                    {p.sku}
                  </span>
                  <span className="text-sm text-emerald-100/90">
                     {' - ' + p.fechaPredicha} → <span className="font-medium">{p.cantidadPredicha}</span>
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-emerald-100/70">
                  {p.modelo} {p.versionModelo} · h={p.horizonte} · gen: {p.tsGeneracion}
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {typeof p.jobId === 'number' && (
                  <Link
                    to={`/predicciones?jobId=${p.jobId}&page=1`}
                    className="text-xs text-emerald-200 hover:underline"
                    title="Ver predicciones de este job"
                  >
                    Job #{p.jobId}
                  </Link>
                )}
                <button
                  type="button"
                  onClick={() => goToHistorialConSku(p.sku)}
                  className="rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-emerald-100/90 hover:bg-white/10"
                >
                  Ver historial del SKU
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
