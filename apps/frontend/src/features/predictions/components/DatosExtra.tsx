// apps/frontend/src/apps/predicciones/components/DatosExtra.tsx
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

  // ---- CARGA 1: dataset amplio para combo + rendimiento por modelo ----
  const paramsListado: PrediccionSearchParams = useMemo(() => ({
    sku:    getParam(sp, 'sku'),
    modelo: getParam(sp, 'modelo'),
    desde:  getParam(sp, 'desde'),
    hasta:  getParam(sp, 'hasta'),
    page: 1,
    pageSize: 500, // alto para evitar quedarnos cortos
    // ultimoJob: true, // usa esto si tu backend lo soporta como default
  }), [sp]);

  const { data: dataListado, isLoading, isError } = usePrediccionesSearch(paramsListado);
  const itemsListado = dataListado?.items ?? [];

  // SKUs únicos (normalizados a "base")
  const skuSet = useMemo(
    () => Array.from(new Set(itemsListado.map(p => getSkuBase(p.sku)))),
    [itemsListado]
  );

  // SKU que viene en la URL (si viene)
  const urlSkuBase = useMemo(() => {
    const s = getParam(sp, 'sku');
    return s ? getSkuBase(s) : undefined;
  }, [sp]);

  // Selección actual para el gráfico derecho
  const [skuSel, setSkuSel] = useState<string | undefined>(undefined);

  // Inicialización de selección
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skuSet, urlSkuBase]);

  // Si la selección deja de existir por cambio de filtros, corregimos
  useEffect(() => {
    if (skuSel && !skuSet.includes(skuSel)) {
      setSkuSel(skuSet[0] ?? undefined);
    }
  }, [skuSet, skuSel]);

  // ---- CARGA 2: dataset focalizado para la serie del SKU ----
  // Evitamos llamar “sin SKU” pasando un valor imposible para que el backend devuelva vacío.
  const paramsSku: PrediccionSearchParams = useMemo(() => ({
    sku: skuSel ?? '__skip__',
    page: 1,
    pageSize: 2000, // grande para cubrir todos los meses/modelos del SKU
    // ultimoJob: true, // si aplica en tu backend
  }), [skuSel]);

  const { data: dataSku } = usePrediccionesSearch(paramsSku);
  const itemsSku = useMemo(
    () => (skuSel ? (dataSku?.items ?? []) : []),
    [dataSku, skuSel]
  );

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
      ) : itemsListado.length === 0 ? (
        <div className="chart-empty">Sin datos para graficar con los filtros actuales.</div>
      ) : (
        <div className="charts-grid">
          {/* Rendimiento por modelo (dataset amplio) */}
          <div className="chart-card">
            <h4 className="chart-title">Rendimiento por modelo</h4>
            <div className="chart-body">
              <ModelPerformanceChart data={itemsListado} />
            </div>
          </div>

          {/* Ventas proyectadas por SKU (dataset focalizado del SKU) */}
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
                itemsSku.length > 0 ? (
                  <ProjectedSalesChart data={itemsSku} sku={skuSel} />
                ) : (
                  <div className="chart-empty" style={{ width: '100%' }}>
                    No hay suficientes datos del SKU seleccionado.
                  </div>
                )
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
