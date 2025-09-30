import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { usePrediccionesSearch } from '../hooks/usePredicciones';
import type { PrediccionSearchParams } from '../types/predicciones';
import ModelPerformanceChart from './charts/ModelPerformanceChart';
import ProjectedSalesChart from './charts/ProjectedSalesChart';
import { getSkuBase } from '../utils/format';

function getParam(sp: URLSearchParams, k: string) {
  const v = sp.get(k);
  return v && v.length ? v : undefined;
}

export default function DatosExtra() {
  const [sp] = useSearchParams();

  const params: PrediccionSearchParams = useMemo(() => ({
    sku: getParam(sp, 'sku'),
    modelo: getParam(sp, 'modelo'),
    desde: getParam(sp, 'desde'),
    hasta: getParam(sp, 'hasta'),
    page: 1,
    pageSize: 200,
  }), [sp]);

  const { data, isLoading, isError } = usePrediccionesSearch(params);
  const items = data?.items ?? [];

  const skuSet = Array.from(new Set(items.map(p => getSkuBase(p.sku))));
  const [skuSel, setSkuSel] = useState<string | undefined>(skuSet[0]);

  if (skuSel && !skuSet.includes(skuSel)) {
    if (skuSet.length) setSkuSel(skuSet[0]);
    else if (skuSel) setSkuSel(undefined);
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="mb-2">
        <h3 className="text-lg font-semibold text-white">Datos extra (gráficas)</h3>
        <p className="text-xs text-emerald-100/70">
          Indicadores calculados sobre las predicciones listadas (arriba). Ajustá los filtros para cambiar estas vistas.
        </p>
      </div>

      {isLoading ? (
        <div className="text-emerald-100/80">Cargando…</div>
      ) : isError ? (
        <div className="rounded-lg border border-rose-400/20 bg-rose-400/10 p-3 text-rose-100">
          Error cargando los datos para las gráficas.
        </div>
      ) : items.length === 0 ? (
        <div className="text-emerald-100/80">Sin datos para graficar con los filtros actuales.</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {/* Rendimiento por modelo */}
          <ModelPerformanceChart data={items} />

          {/* Ventas proyectadas por SKU */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <label className="text-xs text-emerald-100/80">SKU</label>
              <select
                value={skuSel ?? ''}
                onChange={(e) => setSkuSel(e.target.value || undefined)}
                className="rounded border border-white/15 bg-white/10 px-2 py-1 text-sm text-emerald-100/90 outline-none"
              >
                {skuSet.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            {skuSel ? (
              <ProjectedSalesChart data={items} sku={skuSel} />
            ) : (
              <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-emerald-100/80">
                No hay SKUs disponibles para graficar.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
