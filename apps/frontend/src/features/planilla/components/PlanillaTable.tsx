import { createPortal } from 'react-dom';
import { useRef, useState } from 'react';
import type { PlanillaSugerenciaDto, PlanillaVentasDto, PlanillaVentasParams } from '../types/planilla';
import { usePlanillaVentas } from '../hooks/usePlanilla';
import { exportPlanillaExcel } from '../utils/exportPlanilla';
import { DDSTK_MIN_DIAS_CON_STOCK, calcularDdstk, calcularRotDesEstac, calcularVta, celdaRotacionMes, redondearDiasQuiebre, redondearFiabilidad } from '../utils/planillaResumen';
import { useUmbralesTickets } from '../../configuracion/hooks/useConfiguracion';
import { useAuthUser } from '../../auth/hooks/useAuthUser';

// ── Helpers ───────────────────────────────────────────────────────────────────

const MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const mesLabel = (year: number, month: number) => `${MESES[month - 1]}/${String(year).slice(2)}`;

// Issue #145: `ingresoDuranteQuiebre` gana sobre el color por frecuencia --
// mismo criterio que exportPlanilla.ts (celeste, deliberadamente fuera de la
// paleta ámbar/naranja/rojo de quiebre y de los tonos de #65).
//
// Issue #177: exportada para poder probar la rama `sin_datos` sin renderizar
// el componente completo -- mismo patrón que `fiabilidadClass` ya usa acá
// abajo. Función pura sin estado, no afecta fast refresh en dev.
// eslint-disable-next-line react-refresh/only-export-components
export function estadoMesBg(estado: string, frecuenciaNivel?: string | null, ingresoDuranteQuiebre?: boolean): string {
  if (estado === 'quiebre_parcial') {
    if (ingresoDuranteQuiebre) return 'rgba(41,182,246,0.24)';
    if (frecuenciaNivel === 'baja')  return 'rgba(220,38,38,0.18)';
    if (frecuenciaNivel === 'media') return 'rgba(234,88,12,0.18)';
    return 'rgba(234,179,8,0.18)';
  }
  if (estado === 'sin_stock') return 'rgba(100,116,139,0.18)';
  // Issue #177: el Excel sí pinta `sin_datos` (COLOR_SINDATOS = F1F5F9 en
  // exportPlanilla.ts, una versión mucho más clara del gris de sin_stock) --
  // la web lo dejaba sin color, una asimetría de leyenda (el dato no se
  // pierde: la celda ya muestra un `—` muted con tooltip). Mismo tono de
  // slate que sin_stock pero bastante más tenue, para leer "no hay dato" sin
  // competir con el resto de la paleta de estado.
  if (estado === 'sin_datos') return 'rgba(100,116,139,0.08)';
  // Issue #130: sólo en las columnas de rotación -- el mes tuvo stock y ventas
  // pero falta el factor estacional, así que no hay valor corregido que
  // mostrar. Sin esto la celda quedaría vacía y sin explicación.
  if (estado === 'sin_factor') return 'rgba(124,92,180,0.16)';
  return '';
}

// Issue #65: borde (no fondo, para no competir con estadoMesBg/quiebre) para la
// frecuencia de venta por tickets (#61/#63) -- paleta fria, deliberadamente
// distinta de la amarillo/naranja/rojo/gris de quiebre.
function criterioFrecuenciaBorder(criterio?: string | null): string {
  if (criterio === 'historico')        return '3px solid rgba(37,99,235,0.55)';   // azul
  if (criterio === 'promedio')          return '3px solid rgba(139,92,246,0.55)';  // violeta
  if (criterio === 'real_extrapolado')  return '3px solid rgba(20,184,166,0.55)';  // teal
  return '';
}

// Etiqueta del criterio para el tooltip. "real_extrapolado" cubre dos conceptos
// distintos del mail (VentaRealMes vs. Extrapolación) que comparten un solo
// valor de enum -- se reconstruye la etiqueta precisa usando estadoMes, que ya
// viene en la misma fila.
function criterioFrecuenciaLabel(criterio: string | null | undefined, estadoMes: string): string {
  if (criterio === 'historico') return 'Histórico';
  if (criterio === 'promedio')  return 'Promedio';
  if (criterio === 'real_extrapolado') return estadoMes === 'normal' ? 'Venta real' : 'Extrapolado';
  return '—';
}

function fmtResumen(v: number | null): string {
  return v == null ? '—' : v.toFixed(4);
}

// Issue #169: recibe la fiabilidad YA REDONDEADA (redondearFiabilidad), nunca
// el valor crudo -- antes clasificaba sobre el crudo mientras el texto
// mostraba el redondeado, y el badge podía contradecir el número que el
// cliente leía justo en el borde de 70/40. Exportada para poder probar la
// coherencia texto+color en el test de este ticket sin renderizar el
// componente completo -- función pura sin estado, no afecta fast refresh en dev.
// eslint-disable-next-line react-refresh/only-export-components
export function fiabilidadClass(pct: number): string {
  if (pct >= 70) return 'planilla-badge planilla-badge--verde';
  if (pct >= 40) return 'planilla-badge planilla-badge--amarillo';
  return 'planilla-badge planilla-badge--rojo';
}

function qbkClass(dias: number): string {
  if (dias === 0)  return 'planilla-badge planilla-badge--rojo';
  if (dias <= 15)  return 'planilla-badge planilla-badge--amarillo';
  return 'planilla-badge planilla-badge--verde';
}

function EstadoCell({ estado }: { estado?: string }) {
  if (!estado || estado === 'activo') return <span className="planilla-badge planilla-badge--verde">Activo</span>;
  if (estado === 'inactivo')    return <span className="planilla-badge planilla-badge--gris">Inact.</span>;
  if (estado === 'discontinuo') return <span className="planilla-badge planilla-badge--naranja">Desc.</span>;
  return null;
}

function QbkCell({ s }: { s: PlanillaSugerenciaDto | undefined }) {
  if (!s || s.diasHastaQuiebre === null) return <span className="muted">—</span>;
  const dias = redondearDiasQuiebre(s.diasHastaQuiebre);
  return <span className={qbkClass(dias)}>{dias}d</span>;
}

// Issue #178: antes `AeCell` retornaba el `—` genérico apenas
// `rotacionSugerida` era null, ANTES de mirar si `fiabilidadPorcentaje`
// existía -- un acoplamiento implícito que el Excel no tiene (ROT.S y
// Fiabilidad son celdas independientes en exportPlanilla.ts:190-191). Hoy no
// se materializa (0 filas en la réplica con rotacion_sugerida IS NULL AND
// fiabilidad_porcentaje IS NOT NULL) pero si el ETL alguna vez calcula
// fiabilidad sin rotación sugerida, la web la perdía en silencio.
//
// Exportada como función pura -- separa "qué mostrar" (datos) de "cómo
// pintarlo" (JSX), para poder probar los cuatro casos (ambos, sólo rotación,
// sólo fiabilidad, ninguno) sin renderizar el componente. Mismo patrón que
// `fiabilidadClass`/`estadoMesBg` ya usan en este archivo.
// eslint-disable-next-line react-refresh/only-export-components
export function resolveAeCell(s: PlanillaSugerenciaDto | undefined): {
  rotacionLabel: string | null;
  fiabilidad: { pct: number; className: string } | null;
} | null {
  if (!s || (s.rotacionSugerida === null && s.fiabilidadPorcentaje === null)) return null;
  return {
    rotacionLabel: s.rotacionSugerida !== null ? s.rotacionSugerida.toFixed(4) : null,
    // Issue #169: un único redondeo fuente-de-verdad -- el texto y el color
    // del badge tienen que coincidir siempre, incluso en el borde.
    fiabilidad: s.fiabilidadPorcentaje !== null
      ? (() => {
          const fiabRedondeada = redondearFiabilidad(s.fiabilidadPorcentaje);
          return { pct: fiabRedondeada, className: fiabilidadClass(fiabRedondeada) };
        })()
      : null,
  };
}

function AeCell({ s }: { s: PlanillaSugerenciaDto | undefined }) {
  const data = resolveAeCell(s);
  if (!data) return <span className="muted">—</span>;
  return (
    <div className="planilla-ae-cell">
      <span className="planilla-ae-rot">
        {data.rotacionLabel ?? <span className="muted">—</span>}
      </span>
      {data.fiabilidad && (
        <span className={data.fiabilidad.className}>{data.fiabilidad.pct}%</span>
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

type LeyendaEntry = { className: string; label: string; tip: string };

const ESTADO_ENTRIES: LeyendaEntry[] = [
  {
    className: 'planilla-leyenda-normal',
    label: 'Normal (100% días con stock)',
    tip: 'Estado: Normal\nEl artículo tuvo stock el 100% de los días naturales del mes.',
  },
  {
    className: 'planilla-leyenda-quiebre-alta',
    label: 'Quiebre alta freq',
    tip:
      'Estado: Quiebre, frecuencia alta\n' +
      'Hubo días sin stock en el mes, pero el artículo vende casi todos\n' +
      'los días del año (clasificación anual). La rotación ajustada usa\n' +
      'ventas ÷ días con stock, igual que en un mes normal.',
  },
  {
    className: 'planilla-leyenda-quiebre-media',
    label: 'Quiebre media freq',
    tip:
      'Estado: Quiebre, frecuencia media\n' +
      'Hubo días sin stock en el mes. El artículo tiene una frecuencia\n' +
      'de venta anual intermedia. La rotación ajustada promedia\n' +
      '(ventas÷días_con_stock) y (ventas÷días_naturales_mes).',
  },
  {
    className: 'planilla-leyenda-quiebre-baja',
    label: 'Quiebre baja freq',
    tip:
      'Estado: Quiebre, frecuencia baja\n' +
      'Hubo días sin stock en el mes. El artículo vende pocas veces al\n' +
      'año. La rotación ajustada usa ventas ÷ días naturales del mes\n' +
      '(más conservador, evita sobreestimar por los pocos días con stock).',
  },
  {
    className: 'planilla-leyenda-ingreso',
    label: 'Quiebre con ingreso de stock',
    tip:
      'Estado: Quiebre con ingreso de stock (importación)\n' +
      'Hubo días sin stock en el mes, pero en algún momento entró stock\n' +
      '(el stock diario total pasó de 0 a positivo). La venta baja ese mes\n' +
      'no significa que el artículo no venda -- no había qué vender hasta\n' +
      'que llegó la importación.',
  },
  {
    className: 'planilla-leyenda-sinstock',
    label: 'Sin stock (mes completo)',
    tip: 'Estado: Sin stock\nEl artículo no tuvo stock ningún día del mes -- no hay rotación real calculable ese mes.',
  },
  {
    // Issue #177: mismo hueco que el Excel ya resuelve en su hoja Criterios
    // ("Gris claro") -- la web pintaba `sin_datos` sin color y sin entrada en
    // la leyenda general, aunque la celda ya avisaba con un `—` muted y un
    // tooltip propio.
    className: 'planilla-leyenda-sindatos',
    label: 'Sin datos',
    tip: 'Estado: Sin datos\nEl artículo no existía o no hay información de ese mes (sin fila calculada). La celda queda vacía.',
  },
  {
    className: 'planilla-leyenda-sinfactor',
    label: 'Sin factor estacional',
    tip:
      'Sólo en las columnas de rotación mensual.\n' +
      'El mes tuvo stock y ventas, pero el artículo no tiene factor\n' +
      'estacional cargado para ese mes, así que no hay rotación\n' +
      'corregida que mostrar. La rotación sin corregir aparece en el\n' +
      'tooltip de la celda y en la hoja "Detalle de cálculo" del Excel.\n' +
      'Un mes con quiebre y venta 0 NO cae acá: el factor sí está\n' +
      'cargado y la celda muestra 0.',
  },
];

// Los umbrales son configurables en runtime (/configuracion, admin-only) --
// GET /configuracion/umbrales-tickets es admin-only en el backend (issue #22
// fija el patrón: paginas con ambos roles deben pasar `enabled: isAdmin` en
// vez de tocar el interceptor). Para duenoDeEmpresa no hay valor real
// disponible sin violar ese límite -- en vez de arriesgar un número
// hardcodeado que puede quedar mintiendo apenas un admin lo cambie, se
// muestra el criterio sin número concreto.
function frecuenciaEntries(umbrales: { bajoMax: number; altoMin: number } | null): LeyendaEntry[] {
  if (!umbrales) {
    return [
      {
        className: 'planilla-leyenda-frecuencia-historico',
        label: 'Histórico (pocos tickets)',
        tip:
          'Criterio: Histórico\n' +
          'El mes tuvo pocos tickets (días con venta) -- muy pocos datos para\n' +
          'confiar en el mes solo. Se usa el promedio de los últimos 12\n' +
          'meses cerrados. Umbral exacto visible para administrador en /configuracion.',
      },
      {
        className: 'planilla-leyenda-frecuencia-promedio',
        label: 'Promedio (tickets intermedios)',
        tip:
          'Criterio: Promedio\n' +
          'El mes tuvo una cantidad intermedia de tickets. Se promedia el\n' +
          'Histórico con el valor real del mes (o su extrapolación si hubo\n' +
          'quiebre de stock).',
      },
      {
        className: 'planilla-leyenda-frecuencia-real',
        label: 'Venta real / Extrapolado (muchos tickets)',
        tip:
          'Criterio: Venta real / Extrapolado\n' +
          'El mes tuvo suficientes días de venta para confiar en el número\n' +
          'tal cual. Si hubo quiebre, la venta se proyecta al mes completo:\n' +
          'cuanto menos duró el stock más se proyecta, pero nunca más del\n' +
          'doble de lo vendido.',
      },
    ];
  }

  const { bajoMax, altoMin } = umbrales;
  const promedioDesde = bajoMax + 1;
  const promedioHasta = altoMin - 1;
  // Con umbrales adyacentes (ej. bajoMax=3, altoMin=4) no queda ningún valor
  // entero de tickets en el medio -- el criterio "promedio" nunca se asigna
  // con esa config. Se marca explícito en vez de mostrar un rango invertido
  // como "4-3 tickets".
  const hayPromedio = promedioDesde <= promedioHasta;
  const rangoPromedio = promedioDesde === promedioHasta ? `${promedioDesde}` : `${promedioDesde}-${promedioHasta}`;
  return [
    {
      className: 'planilla-leyenda-frecuencia-historico',
      label: `Histórico (≤${bajoMax} tickets)`,
      tip:
        'Criterio: Histórico\n' +
        `El mes tuvo ${bajoMax} tickets (días con venta) o menos -- muy pocos\n` +
        'datos para confiar en el mes solo. Se usa el promedio de los\n' +
        'últimos 12 meses cerrados.',
    },
    {
      className: 'planilla-leyenda-frecuencia-promedio',
      label: hayPromedio ? `Promedio (${rangoPromedio} tickets)` : 'Promedio (sin rango con estos umbrales)',
      tip: hayPromedio
        ? 'Criterio: Promedio\n' +
          `El mes tuvo ${rangoPromedio} tickets. Se promedia el Histórico con el valor\n` +
          'real del mes (o su extrapolación si hubo quiebre de stock).'
        : 'Criterio: Promedio\n' +
          `Con los umbrales actuales (≤${bajoMax} / ≥${altoMin}) no queda ningún valor\n` +
          'de tickets en el medio -- este criterio no se asigna hoy.',
    },
    {
      className: 'planilla-leyenda-frecuencia-real',
      label: `Venta real / Extrapolado (≥${altoMin} tickets)`,
      tip:
        'Criterio: Venta real / Extrapolado\n' +
        `El mes tuvo ${altoMin} tickets o más -- suficientes días de venta para\n` +
        'confiar en el número tal cual. Si hubo quiebre, la venta se proyecta\n' +
        'al mes completo: cuanto menos duró el stock más se proyecta, pero\n' +
        'nunca más del doble de lo vendido.',
    },
  ];
}

function Leyenda() {
  // Patrón de #22: `enabled: isAdmin` en vez de tocar el interceptor Axios,
  // que no se debe suprimir globalmente (es señal válida en otros casos).
  const { user } = useAuthUser();
  const isAdmin = user?.role === 'administrador';
  const { data } = useUmbralesTickets(isAdmin);
  const umbrales = isAdmin && data ? { bajoMax: data.ticketsBajoMax, altoMin: data.ticketsAltoMin } : null;

  return (
    <div className="planilla-leyenda">
      <span className="planilla-leyenda-titulo">Estado mensual:</span>
      {ESTADO_ENTRIES.map((entry) => (
        <span key={entry.className} className={`planilla-leyenda-item ${entry.className}`}>
          <Tip label={entry.label} tip={entry.tip} />
        </span>
      ))}
      <span className="planilla-leyenda-titulo">Criterio de frecuencia (borde izq.):</span>
      {frecuenciaEntries(umbrales).map((entry) => (
        <span key={entry.className} className={`planilla-leyenda-item ${entry.className}`}>
          <Tip label={entry.label} tip={entry.tip} />
        </span>
      ))}
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
  const totalCols  = 3 + mesHeaders.length * 2 + 6; // SKU+Desc, Cód.Barras, Género, [Vta months], [Rot months], Rot.DesEstac., Estado, VTA, DDSTK, ROT.S, QBK

  const handleExport = async () => {
    setExporting(true);
    try {
      await exportPlanillaExcel(params, sugerencias);
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
                <Tip label="Cód. Barras" tip="Código de barras del artículo." />
              </th>
              <th>
                <Tip label="Género" tip="Género del artículo según el catálogo." />
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
                                // Issue #175: faltaban el celeste de #145 (ingreso de
                                // stock durante quiebre) y el gris claro de sin_datos --
                                // mismo texto que ESTADO_ENTRIES y la hoja Criterios del
                                // Excel usan para estos dos colores.
                                : `Vta.${mesLabel(m.year, m.month)} — Unidades vendidas\nTotal de unidades vendidas en el mes.\nAmarillo = quiebre alta freq · Naranja = quiebre media · Rojo = quiebre baja freq · Celeste = ingreso de stock durante quiebre · Gris = sin stock · Gris claro = sin datos`
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
                                ? `${mesLabel(m.year, m.month)} — Mes de referencia\nRotación corregida por estacionalidad.\nNo entra en el promedio de Rot. DesEstac.`
                                // Issue #175: faltaba el celeste de #145 (ya tenía el
                                // lila de #130) -- mismo texto que ESTADO_ENTRIES.
                                : `${mesLabel(m.year, m.month)} — Rotación diaria corregida por estacionalidad\nEs el valor que promedia Rot. DesEstac., así que ese promedio se puede verificar con estas celdas.\nLa rotación sin corregir está en el tooltip de cada celda.\nAmarillo = quiebre alta freq · Naranja = quiebre media · Rojo = quiebre baja freq · Celeste = ingreso de stock durante quiebre · Gris = sin stock · Lila = sin factor estacional`
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
                    '  · Meses con quiebre: rotación ajustada por frecuencia ÷ factor estacional\n' +
                    '  · Meses con quiebre y venta 0: participan con rotación 0 (dato real, no se descartan)\n' +
                    '  · Meses sin stock o sin factor estacional cargado: excluidos'
                  }
                />
              </th>
              <th>
                <Tip
                  label="Estado"
                  tip={'Estado del artículo en el catálogo.\n  · Activo — en venta normal\n  · Inact. — temporalmente inactivo\n  · Desc. — discontinuado, sin reposición'}
                />
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
              <th className="planilla-col-summary">
                <Tip
                  label="DDSTK"
                  tip={
                    'Demanda Diaria con Stock\n' +
                    'Fórmula: Σ ventas de los meses con stock ÷ Σ días con stock de esos meses\n' +
                    'Tasa de venta diaria histórica promedio del artículo,\n' +
                    'calculada sobre los 13 meses de la ventana.\n' +
                    'Un mes sin ningún día de stock no aporta venta al numerador.\n\n' +
                    `— = menos de ${DDSTK_MIN_DIAS_CON_STOCK} días con stock en toda la ventana\n` +
                    '(muy poca base para confiar en el número).'
                  }
                />
              </th>
              <th className="planilla-col-summary">
                <Tip
                  label="ROT.S"
                  tip={
                    'Rotación Sugerida\n' +
                    'Promedio ponderado de la rotación de meses cerrados con stock\n' +
                    '(normal: rotación real; quiebre: rotación ajustada) —\n' +
                    'los meses sin ventas cuentan con rotación 0, no se descartan\n' +
                    '(pesos lineales: más reciente = mayor peso, hasta 12 meses cerrados —\n' +
                    'el mes de referencia en curso siempre queda afuera).\n\n' +
                    'Badge de fiabilidad:\n' +
                    '  Verde  ≥ 70% — rotación estable\n' +
                    '  Amarillo 40–69% — variabilidad moderada\n' +
                    '  Rojo  < 40% — alta variabilidad\n\n' +
                    '— = menos de 3 meses cerrados con datos disponibles.'
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
                    '— = sin ROT.S calculada o ROT.S en cero, o el último dato\n' +
                    'de stock del artículo tiene más de 7 días de antigüedad.'
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
                  <td><span className="skeleton skel-100" /></td>
                  <td><span className="skeleton skel-80" /></td>
                  {Array.from({ length: 26 }).map((__, j) => <td key={j}><span className="skeleton skel-40" /></td>)}
                  <td><span className="skeleton skel-60" /></td>
                  <td><span className="skeleton skel-40" /></td>
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
                const rd  = fmtResumen(calcularRotDesEstac(row.meses));
                const dd  = fmtResumen(calcularDdstk(row.meses));
                const vta = calcularVta(row.meses);
                return (
                  <tr key={row.sku}>
                    <td className="planilla-sticky-col planilla-col-sku">
                      <span className="planilla-sku">{row.sku}</span>
                      <span className="planilla-desc">{row.descripcion ?? '—'}</span>
                    </td>
                    <td className="planilla-col-barras">{row.codigoBarras ?? '—'}</td>
                    <td>{row.generoDescripcion ?? '—'}</td>

                    {row.meses.map((mes, idx) => (
                      <td
                        key={`vta-${mes.year}-${mes.month}`}
                        className="planilla-col-mes"
                        style={{
                          backgroundColor: estadoMesBg(mes.estadoMes, mes.frecuenciaNivel, mes.ingresoDuranteQuiebre),
                          borderLeft: criterioFrecuenciaBorder(mes.criterioFrecuencia),
                        }}
                        title={
                          mes.estadoMes === 'sin_datos'
                            ? `Vta.${mesLabel(mes.year, mes.month)} · Sin datos (mes sin fila calculada)`
                            : `Vta.${mesLabel(mes.year, mes.month)} · ${mes.ventasCantidad ?? 0} uds. · Criterio: ${criterioFrecuenciaLabel(mes.criterioFrecuencia, mes.estadoMes)}` +
                              (mes.ingresoDuranteQuiebre ? ' · Entró stock (importación) durante el mes' : '')
                        }
                      >
                        <span style={idx === lastMesIdx ? { opacity: 0.6, fontStyle: 'italic' } : undefined}>
                          {mes.estadoMes === 'sin_datos'
                            ? <span className="muted">—</span>
                            : (mes.ventasCantidad ?? 0).toLocaleString('es-UY')}
                        </span>
                      </td>
                    ))}

                    {row.meses.map((mes, idx) => {
                      // Issue #130: muestra la rotación desestacionalizada, que
                      // es lo que promedia Rot. DesEstac. -- antes mostraba la
                      // cruda y el promedio no se podía verificar a mano.
                      const celda = celdaRotacionMes(mes);
                      return (
                        <td
                          key={`rot-${mes.year}-${mes.month}`}
                          className="planilla-col-mes"
                          style={{ backgroundColor: estadoMesBg(celda.estado, mes.frecuenciaNivel, mes.ingresoDuranteQuiebre) }}
                          title={
                            celda.estado === 'sin_datos'
                              ? `${mesLabel(mes.year, mes.month)} · Sin datos (mes sin fila calculada)`
                              : celda.estado === 'sin_factor'
                                ? `${mesLabel(mes.year, mes.month)} · Sin factor estacional cargado para este mes — la rotación sin corregir es ${(mes.rotacionDiariaReal ?? 0).toFixed(4)}`
                                : `${mesLabel(mes.year, mes.month)} · ${mes.diasConStock ?? 0}/${mes.diasNaturalesMes} días con stock · ${mes.ventasCantidad ?? 0} uds. · sin corregir: ${(mes.rotacionDiariaReal ?? 0).toFixed(4)}` +
                                  (mes.ingresoDuranteQuiebre ? ' · Entró stock (importación) durante el mes' : '')
                          }
                        >
                          <span style={idx === lastMesIdx ? { opacity: 0.6, fontStyle: 'italic' } : undefined}>
                            {celda.valor != null ? celda.valor.toFixed(4) : <span className="muted">—</span>}
                          </span>
                        </td>
                      );
                    })}

                    <td className={`planilla-col-summary${rd === '—' ? ' sin-datos' : ''}`}>{rd}</td>
                    <td><EstadoCell estado={row.estadoArticulo} /></td>
                    <td className="planilla-col-summary">{vta.toLocaleString('es-UY')}</td>
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
