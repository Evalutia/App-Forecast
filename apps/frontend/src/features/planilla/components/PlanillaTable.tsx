import { createPortal } from 'react-dom';
import { useRef, useState } from 'react';
import type { PlanillaMesDto, PlanillaSugerenciaDto, PlanillaVentasDto, PlanillaVentasParams } from '../types/planilla';
import { usePlanillaVentas } from '../hooks/usePlanilla';
import { exportPlanillaExcel } from '../utils/exportPlanilla';

// ── Helpers ───────────────────────────────────────────────────────────────────

const MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const mesLabel = (year: number, month: number) => `${MESES[month - 1]}/${String(year).slice(2)}`;

function estadoMesBg(estado: string, frecuenciaNivel?: string | null): string {
  if (estado === 'quiebre_parcial') {
    if (frecuenciaNivel === 'baja')  return 'rgba(220,38,38,0.18)';
    if (frecuenciaNivel === 'media') return 'rgba(234,88,12,0.18)';
    return 'rgba(234,179,8,0.18)';
  }
  if (estado === 'sin_stock') return 'rgba(100,116,139,0.18)';
  return '';
}

function calcRotDesEstac(meses: PlanillaMesDto[]): string {
  const closed = meses.slice(0, -1);
  const vals: number[] = [];
  for (const m of closed) {
    if (m.estadoMes === 'normal' && m.rotacionDiariaDesestacionalizada != null) {
      vals.push(m.rotacionDiariaDesestacionalizada);
    } else if (m.estadoMes === 'quiebre_parcial' && m.rotacionAjustada != null) {
      if (m.rotacionDiariaDesestacionalizada != null && m.rotacionDiariaReal != null && m.rotacionDiariaReal > 0)
        vals.push(m.rotacionAjustada * (m.rotacionDiariaDesestacionalizada / m.rotacionDiariaReal));
      else
        vals.push(m.rotacionAjustada);
    }
  }
  if (vals.length === 0) return '—';
  return (vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(4);
}

function calcDdstk(meses: PlanillaMesDto[]): string {
  const totalVentas = meses.reduce((s, m) => s + Number(m.ventasCantidad), 0);
  const totalDias   = meses.reduce((s, m) => s + m.diasConStock, 0);
  if (totalDias === 0) return '—';
  return (totalVentas / totalDias).toFixed(4);
}

// VTA: suma de ventasCantidad de los 12 meses cerrados (excluye el mes de referencia)
function calcVta(meses: PlanillaMesDto[]): number {
  return meses.slice(0, -1).reduce((s, m) => s + Number(m.ventasCantidad), 0);
}

function fiabilidadClass(pct: number): string {
  if (pct >= 70) return 'planilla-badge planilla-badge--verde';
  if (pct >= 40) return 'planilla-badge planilla-badge--amarillo';
  return 'planilla-badge planilla-badge--rojo';
}

function qbkClass(dias: number): string {
  if (dias === 0)  return 'planilla-badge planilla-badge--rojo';
  if (dias <= 15)  return 'planilla-badge planilla-badge--amarillo';
  return 'planilla-badge planilla-badge--verde';
}

function QbkCell({ s }: { s: PlanillaSugerenciaDto | undefined }) {
  if (!s || s.diasHastaQuiebre === null) return <span className="muted">—</span>;
  const dias = Math.round(s.diasHastaQuiebre);
  return <span className={qbkClass(dias)}>{dias}d</span>;
}

function AeCell({ s }: { s: PlanillaSugerenciaDto | undefined }) {
  if (!s || s.rotacionSugerida === null) return <span className="muted">—</span>;
  return (
    <div className="planilla-ae-cell">
      <span className="planilla-ae-rot">{s.rotacionSugerida.toFixed(4)}</span>
      {s.fiabilidadPorcentaje !== null && (
        <span className={fiabilidadClass(s.fiabilidadPorcentaje)}>
          {s.fiabilidadPorcentaje.toFixed(0)}%
        </span>
      )}
    </div>
  );
}

// ── Tooltip via portal (escapes overflow-x: auto) ─────────────────────────────

const TIP_STYLE: React.CSSProperties = {
  position: 'fixed',
  zIndex: 9999,
  background: '#0d1f14',
  border: '1px solid rgba(52,196,143,0.28)',
  borderRadius: '10px',
  padding: '10px 14px',
  fontSize: '12px',
  lineHeight: '1.65',
  color: '#f0f5f2',
  whiteSpace: 'pre-line',
  maxWidth: '300px',
  boxShadow: '0 12px 32px rgba(0,0,0,0.65)',
  pointerEvents: 'none',
  transform: 'translateX(-50%)',
};

function Tip({ label, tip, style }: { label: React.ReactNode; tip: string; style?: React.CSSProperties }) {
  const iconRef = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);

  const show = (e: React.MouseEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setPos({ x: Math.min(r.left + r.width / 2, window.innerWidth - 160), y: r.bottom + 6 });
  };

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, ...style }}>
      {label}
      <span
        ref={iconRef}
        style={{ cursor: 'help', opacity: 0.5, fontSize: '11px', lineHeight: 1 }}
        onMouseEnter={show}
        onMouseLeave={() => setPos(null)}
      >
        ⓘ
      </span>
      {pos && createPortal(
        <div style={{ ...TIP_STYLE, left: pos.x, top: pos.y }}>{tip}</div>,
        document.body
      )}
    </span>
  );
}

// ── Legend ────────────────────────────────────────────────────────────────────

function Leyenda() {
  return (
    <div className="planilla-leyenda">
      <span className="planilla-leyenda-titulo">Estado mensual:</span>
      <span className="planilla-leyenda-item planilla-leyenda-normal">Normal (≥90% días con stock)</span>
      <span className="planilla-leyenda-item planilla-leyenda-quiebre-alta">Quiebre alta freq</span>
      <span className="planilla-leyenda-item planilla-leyenda-quiebre-media">Quiebre media freq</span>
      <span className="planilla-leyenda-item planilla-leyenda-quiebre-baja">Quiebre baja freq</span>
      <span className="planilla-leyenda-item planilla-leyenda-sinstock">Sin stock (mes completo)</span>
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

type Props = {
  params: PlanillaVentasParams;
  onPageChange: (page: number) => void;
  sugerencias: Map<string, PlanillaSugerenciaDto>;
  sugerenciasLoading: boolean;
};

export default function PlanillaTable({ params, onPageChange, sugerencias, sugerenciasLoading }: Props) {
  const { data, isLoading, isFetching, isError } = usePlanillaVentas(params);
  const [exporting, setExporting] = useState(false);

  const items      = data?.items ?? [];
  const total      = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / params.pageSize));
  const mesHeaders: { year: number; month: number }[] = items[0]?.meses ?? [];
  const lastMesIdx = mesHeaders.length - 1;
  const totalCols  = 3 + mesHeaders.length * 2 + 4; // SKU+Desc, Género, VTA, Vta months, rot months, Rot.DesEstac., DDSTK, AE, QBK

  const handleExport = async () => {
    setExporting(true);
    try {
      await exportPlanillaExcel(params);
    } finally {
      setExporting(false);
    }
  };

  return (
    <section className="card table-card">
      {/* Top bar: legend + export button */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
        <Leyenda />
        <button
          type="button"
          className="pg-btn pg-btn-sm"
          onClick={handleExport}
          disabled={exporting || isLoading || total === 0}
          style={{ flexShrink: 0 }}
        >
          {exporting ? 'Exportando…' : '↓ Exportar Excel'}
        </button>
      </div>

      <div className="table-wrap" style={{ overflowX: 'auto' }}>
        <table className="table planilla-tabla">
          <thead>
            <tr>
              <th className="planilla-sticky-col planilla-col-sku">
                <Tip
                  label="SKU / Descripción"
                  tip="Código de artículo y descripción del producto."
                />
              </th>
              <th>
                <Tip label="Género" tip="Género del artículo según el catálogo." />
              </th>
              <th className="planilla-col-summary">
                <Tip
                  label="VTA"
                  tip={
                    'Ventas Totales del período\n' +
                    'Suma de unidades vendidas en los 12 meses cerrados.\n' +
                    'Excluye el mes de referencia más reciente.'
                  }
                />
              </th>

              {isLoading
                ? Array.from({ length: 26 }).map((_, i) => (
                    <th key={i}><span className="skeleton skel-40" /></th>
                  ))
                : (<>
                    {mesHeaders.map((m, idx) => {
                      const esRef = idx === lastMesIdx;
                      return (
                        <th
                          key={`vta-${m.year}-${m.month}`}
                          className="planilla-col-mes"
                          style={esRef ? { opacity: 0.65 } : undefined}
                        >
                          <Tip
                            label={<span style={esRef ? { fontStyle: 'italic' } : undefined}>Vta.{mesLabel(m.year, m.month)}</span>}
                            tip={
                              esRef
                                ? `Vta.${mesLabel(m.year, m.month)} — Mes de referencia\nUnidades vendidas (mes en curso, incompleto).`
                                : `Vta.${mesLabel(m.year, m.month)} — Unidades vendidas\nTotal de unidades vendidas en el mes.\nAmarillo = quiebre alta freq · Naranja = quiebre media · Rojo = quiebre baja freq · Gris = sin stock`
                            }
                          />
                        </th>
                      );
                    })}
                    {mesHeaders.map((m, idx) => {
                      const esRef = idx === lastMesIdx;
                      return (
                        <th
                          key={`rot-${m.year}-${m.month}`}
                          className="planilla-col-mes"
                          style={esRef ? { opacity: 0.65 } : undefined}
                        >
                          <Tip
                            label={<span style={esRef ? { fontStyle: 'italic' } : undefined}>{mesLabel(m.year, m.month)}</span>}
                            tip={
                              esRef
                                ? `${mesLabel(m.year, m.month)} — Mes de referencia\nNo entra en el promedio de Rot. DesEstac.\nFórmula: ventas ÷ días_con_stock`
                                : `${mesLabel(m.year, m.month)} — Rotación diaria real\nFórmula: ventas_mes ÷ días_con_stock\nAmarillo = quiebre alta freq · Naranja = quiebre media · Rojo = quiebre baja freq · Gris = sin stock`
                            }
                          />
                        </th>
                      );
                    })}
                  </>)}

              <th className="planilla-col-summary">
                <Tip
                  label="Rot. DesEstac."
                  tip={
                    'Rotación diaria promedio corregida por estacionalidad.\n' +
                    'Promedio de meses cerrados, excluyendo el mes de referencia.\n' +
                    '  · Meses normales: rotación real ÷ factor estacional del mes\n' +
                    '  · Meses con quiebre: rotación ajustada por frecuencia × factor estacional\n' +
                    '  · Meses sin stock o sin factor: excluidos'
                  }
                />
              </th>
              <th className="planilla-col-summary">
                <Tip
                  label="DDSTK"
                  tip={
                    'Demanda Diaria con Stock\n' +
                    'Fórmula: Σ ventas del período ÷ Σ días con stock del período\n' +
                    'Tasa de venta diaria histórica promedio del artículo,\n' +
                    'calculada sobre los 13 meses de la ventana.'
                  }
                />
              </th>
              <th className="planilla-col-summary">
                <Tip
                  label="ROT.S"
                  tip={
                    'Rotación Sugerida\n' +
                    'Promedio ponderado de la rotación real en meses normales\n' +
                    '(pesos lineales: más reciente = mayor peso, hasta 13 meses).\n\n' +
                    'Badge de fiabilidad:\n' +
                    '  Verde  ≥ 70% — rotación estable\n' +
                    '  Amarillo 40–69% — variabilidad moderada\n' +
                    '  Rojo  < 40% — alta variabilidad\n\n' +
                    '— = menos de 3 meses con stock normal disponibles.'
                  }
                />
              </th>
              <th className="planilla-col-summary">
                <Tip
                  label="QBK"
                  tip={
                    'Días estimados hasta quiebre de stock\n' +
                    'Fórmula: stock_actual ÷ rotación_sugerida (ROT.S)\n\n' +
                    'Badge de urgencia:\n' +
                    '  Rojo    = 0d — sin stock ya\n' +
                    '  Amarillo ≤ 15d — menos de 2 semanas (lead time típico)\n' +
                    '  Verde   > 15d — margen suficiente\n\n' +
                    '— = sin datos suficientes para calcular.'
                  }
                />
              </th>
            </tr>
          </thead>

          <tbody>
            {isLoading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i}>
                  <td className="planilla-sticky-col"><span className="skeleton skel-120" /></td>
                  <td><span className="skeleton skel-80" /></td>
                  <td><span className="skeleton skel-60" /></td>
                  {Array.from({ length: 26 }).map((__, j) => <td key={j}><span className="skeleton skel-40" /></td>)}
                  <td><span className="skeleton skel-60" /></td>
                  <td><span className="skeleton skel-60" /></td>
                  <td><span className="skeleton skel-60" /></td>
                  <td><span className="skeleton skel-60" /></td>
                </tr>
              ))
            ) : isError ? (
              <tr>
                <td colSpan={totalCols} className="muted" style={{ textAlign: 'center', padding: '1.5rem 0' }}>
                  No se pudo cargar la planilla.
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={totalCols} className="muted" style={{ textAlign: 'center', padding: '1.5rem 0' }}>
                  No se encontraron artículos con los filtros aplicados.
                </td>
              </tr>
            ) : (
              items.map((row: PlanillaVentasDto) => {
                const rd  = calcRotDesEstac(row.meses);
                const dd  = calcDdstk(row.meses);
                const vta = calcVta(row.meses);
                return (
                  <tr key={row.sku}>
                    <td className="planilla-sticky-col planilla-col-sku">
                      <span className="planilla-sku">{row.sku}</span>
                      <span className="planilla-desc">{row.descripcion ?? '—'}</span>
                    </td>
                    <td>{row.generoDescripcion ?? '—'}</td>
                    <td className="planilla-col-summary">{vta.toLocaleString('es-UY')}</td>

                    {row.meses.map((mes, idx) => (
                      <td
                        key={`vta-${mes.year}-${mes.month}`}
                        className="planilla-col-mes"
                        style={{ backgroundColor: estadoMesBg(mes.estadoMes, mes.frecuenciaNivel) }}
                        title={`Vta.${mesLabel(mes.year, mes.month)} · ${mes.ventasCantidad} uds.`}
                      >
                        <span style={idx === lastMesIdx ? { opacity: 0.6, fontStyle: 'italic' } : undefined}>
                          {Number(mes.ventasCantidad).toLocaleString('es-UY')}
                        </span>
                      </td>
                    ))}

                    {row.meses.map((mes, idx) => (
                      <td
                        key={`rot-${mes.year}-${mes.month}`}
                        className="planilla-col-mes"
                        style={{ backgroundColor: estadoMesBg(mes.estadoMes, mes.frecuenciaNivel) }}
                        title={`${mesLabel(mes.year, mes.month)} · ${mes.diasConStock}/${mes.diasNaturalesMes} días con stock · ${mes.ventasCantidad} uds.`}
                      >
                        <span style={idx === lastMesIdx ? { opacity: 0.6, fontStyle: 'italic' } : undefined}>
                          {mes.rotacionDiariaReal != null ? mes.rotacionDiariaReal.toFixed(4) : '0.0000'}
                        </span>
                      </td>
                    ))}

                    <td className={`planilla-col-summary${rd === '—' ? ' sin-datos' : ''}`}>{rd}</td>
                    <td className={`planilla-col-summary${dd === '—' ? ' sin-datos' : ''}`}>{dd}</td>
                    <td className="planilla-col-summary">
                      {sugerenciasLoading
                        ? <span className="skeleton skel-60" />
                        : <AeCell s={sugerencias.get(row.sku)} />}
                    </td>
                    <td className="planilla-col-summary">
                      {sugerenciasLoading
                        ? <span className="skeleton skel-60" />
                        : <QbkCell s={sugerencias.get(row.sku)} />}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="pager">
        <div className="muted">
          {isFetching && !isLoading
            ? 'Actualizando…'
            : `${total} artículos · Página ${params.page} de ${totalPages}`}
        </div>
        <div className="pager-buttons">
          <button
            className="pager-btn"
            disabled={params.page <= 1}
            onClick={() => onPageChange(params.page - 1)}
          >
            Anterior
          </button>
          <button
            className="pager-btn"
            disabled={params.page >= totalPages}
            onClick={() => onPageChange(params.page + 1)}
          >
            Siguiente
          </button>
        </div>
      </div>
    </section>
  );
}
