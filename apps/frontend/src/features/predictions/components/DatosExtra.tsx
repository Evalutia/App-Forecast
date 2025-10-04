import { useMemo, useState, useEffect } from 'react';
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

  // SKUs únicos (normalizados a "base")
  const skuSet = useMemo(
    () => Array.from(new Set(items.map(p => getSkuBase(p.sku)))),
    [items]
  );

  // SKU que viene en la URL (si viene)
  const urlSkuBase = useMemo(() => {
    const s = getParam(sp, 'sku');
    return s ? getSkuBase(s) : undefined;
  }, [sp]);

  // Selección actual para el gráfico derecho
  const [skuSel, setSkuSel] = useState<string | undefined>(undefined);

  // ✅ Inicialización (solo cuando cambian los datos/filtros o la URL),
  // no dependemos de "skuSel" para NO pisar la elección del usuario.
  useEffect(() => {
    if (skuSet.length === 0) {
      setSkuSel(undefined);
      return;
    }
    if (skuSel === undefined) {
      const preferred =
        (urlSkuBase && skuSet.includes(urlSkuBase)) ? urlSkuBase : skuSet[0];
      setSkuSel(preferred);
    }
  }, [skuSet, urlSkuBase]); // <-- sin skuSel

  // ✅ Si la selección actual deja de existir por un cambio de filtros, corregimos.
  useEffect(() => {
    if (skuSel && !skuSet.includes(skuSel)) {
      setSkuSel(skuSet[0] ?? undefined);
    }
  }, [skuSet, skuSel]);

  return (
    <section className="extra-card">
      <p className="extra-subtitle">
        Indicadores calculados sobre las predicciones listadas (arriba).
        Ajustá los filtros para cambiar estas vistas.
      </p>

      {isLoading ? (
        <div className="chart-loading">Cargando…</div>
      ) : isError ? (
        <div className="chart-error">Error cargando los datos para las gráficas.</div>
      ) : items.length === 0 ? (
        <div className="chart-empty">Sin datos para graficar con los filtros actuales.</div>
      ) : (
        <div className="charts-grid">
          {/* Rendimiento por modelo */}
          <div className="chart-card">
            <h4 className="chart-title">Rendimiento por modelo</h4>
            <div className="chart-body">
              <ModelPerformanceChart data={items} />
            </div>
          </div>

          {/* Ventas proyectadas por SKU */}
          <div className="chart-card">
            <div className="chart-controls">
              <span className="chart-label">SKU</span>
              <select
                value={skuSel ?? ''}
                onChange={(e) => setSkuSel(e.target.value || undefined)}
                className="chart-select"
              >
                {skuSet.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div className="chart-body">
              {skuSel ? (
                <ProjectedSalesChart data={items} sku={skuSel} />
              ) : (
                <div className="chart-empty" style={{ width: '100%' }}>
                  No hay SKUs disponibles para graficar.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
