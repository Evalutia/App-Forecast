// apps/frontend/src/apps/predicciones/components/DatosExtra.tsx
import { useMemo, useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { usePrediccionesSearch, useVentaSkuResumen } from '../hooks/usePredicciones';
import { formatNumber } from '../utils/format';
import type { PrediccionSearchParams } from '../types/predicciones';
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

  const { data: resumenSku, isLoading: loadingResumen, isError: errorResumen } = useVentaSkuResumen(skuSel);

  const fmtNum = (v: number | null | undefined) => {
    return formatNumber(v);
  };
  const fmtPct = (v: number | null | undefined) => {
    if (typeof v !== 'number' || Number.isNaN(v)) return '—';
    return `${v.toFixed(2)}%`;
  };

  return (
    <section className="extra-card">
      <p className="extra-subtitle">
        Seleccione un SKU para ver un resumen de las ventas y la proyección trimestral 
        o esriba el nombre del SKU en el filtro de la sección "Historial de predicciones".
      </p>

      {isLoading ? (
        <div className="chart-loading">Cargando…</div>
      ) : isError ? (
        <div className="chart-error">Error cargando los datos para las gráficas.</div>
      ) : itemsListado.length === 0 ? (
        <div className="chart-empty">Sin datos para graficar con los filtros actuales.</div>
      ) : (
        <div className="charts-grid">
          {/* Resumen de ventas por SKU */}
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
            <div className="chart-body sku-resumen-body">
              {!skuSel ? (
                <div className="chart-empty" style={{ width: '100%' }}>
                  No hay SKUs disponibles.
                </div>
              ) : loadingResumen ? (
                <div className="chart-loading">Cargando resumen…</div>
              ) : errorResumen ? (
                <div className="chart-error">Error cargando el resumen del SKU.</div>
              ) : !resumenSku ? (
                <div className="chart-empty" style={{ width: '100%' }}>
                  Sin resumen disponible.
                </div>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Métrica</th>
                        <th>Valor</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>Fecha de la primera primera observación para predecir</td>
                        <td className="mono">{resumenSku.fechaPrimerObservacion ?? '—'}</td>
                      </tr>
                      <tr>
                        <td>Fecha de la última observación para predecir</td>
                        <td className="mono">{resumenSku.fechaUltimaObservacion ?? '—'}</td>
                      </tr>
                      <tr>
                        <td>Cantidad observaciones</td>
                        <td>{fmtNum(resumenSku.cantidadObservaciones)}</td>
                      </tr>
                      <tr>
                        <td>Mínimo ventas (trimestre)</td>
                        <td>
                          {fmtNum(resumenSku.minimoVentasTrimestral)}
                          {resumenSku.trimestreMinimoVentas ? ` · ${resumenSku.trimestreMinimoVentas}` : ''}
                        </td>
                      </tr>
                      <tr>
                        <td>Máximo ventas (trimestre)</td>
                        <td>
                          {fmtNum(resumenSku.maximoVentasTrimestral)}
                          {resumenSku.trimestreMaximoVentas ? ` · ${resumenSku.trimestreMaximoVentas}` : ''}
                        </td>
                      </tr>
                      <tr>
                        <td>Promedio de ventas por trimestre</td>
                        <td>{fmtNum(resumenSku.promedioVentasTrimestral)}</td>
                      </tr>
                      <tr>
                        <td>Ventas del último trimestre móvil completo</td>
                        <td>
                          {fmtNum(resumenSku.ventasUltimoTrimestre)}
                          {resumenSku.ultimoTrimestre ? ` · ${resumenSku.ultimoTrimestre}` : ''}
                        </td>
                      </tr>
                      <tr>
                        <td>Ventas del último año (12m) móvil</td>
                        <td>{fmtNum(resumenSku.ventasUltimoAnioCalendario)}</td>
                      </tr>
                      <tr>
                        <td>Crecimiento de ventas en el último año móvil</td>
                        <td>{fmtPct(resumenSku.crecimientoVentasUltimoAnio)}</td>
                      </tr>
                      <tr>
                        <td>Crecimiento de ventas en el último trimestre vs mismo trimestre del año móvil anterior</td>
                        <td>{fmtPct(resumenSku.crecimientoVentasUltimoTrimestreVsMismoTrimestreAnioAnterior)}</td>
                      </tr>
                      <tr>
                        <td>Incidencia en porcentaje de ventas totales del último año móvil</td>
                        <td>{fmtPct(resumenSku.incidenciaVentasUltimoAnioPorcentaje)}</td>
                      </tr>
                      <tr>
                        <td>Incidencia en porcentaje de ventas totales del último trimestre móvil</td>
                        <td>{fmtPct(resumenSku.incidenciaVentasUltimoTrimestrePorcentaje)}</td>
                      </tr>
                      <tr>
                        <td>Ranking del producto</td>
                        <td>
                          {typeof resumenSku.rankingUltimoAnio === 'number'
                            ? `${resumenSku.rankingUltimoAnio} de ${resumenSku.totalSkusUltimoAnio}`
                            : '—'}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          {/* Ventas proyectadas por SKU (dataset focalizado del SKU) */}
          <div className="chart-card">
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
