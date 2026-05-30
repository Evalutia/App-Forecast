import type { PlanillaMesDto, PlanillaVentasDto, PlanillaVentasParams } from '../types/planilla';
import { usePlanillaVentas } from '../hooks/usePlanilla';

const MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const mesLabel = (year: number, month: number) => `${MESES[month - 1]}/${String(year).slice(2)}`;

// Colors matching the client Excel: transparent = normal, amber = quiebre, grey = sin_stock
function estadoMesBg(estado: string): string {
  if (estado === 'quiebre_parcial') return 'rgba(234,179,8,0.18)';
  if (estado === 'sin_stock')       return 'rgba(100,116,139,0.18)';
  return '';
}

// AD: average of rotacionDiariaReal for closed normal months (exclude last = reference month)
function calcRotDesEstac(meses: PlanillaMesDto[]): string {
  const closed  = meses.slice(0, -1);                           // drop last (reference)
  const normales = closed.filter(m => m.estadoMes === 'normal' && m.rotacionDiariaReal != null);
  if (normales.length === 0) return '—';
  const avg = normales.reduce((s, m) => s + (m.rotacionDiariaReal ?? 0), 0) / normales.length;
  return avg.toFixed(4);
}

// AL: total ventas / total días con stock across all months
function calcDdstk(meses: PlanillaMesDto[]): string {
  const totalVentas = meses.reduce((s, m) => s + Number(m.ventasCantidad), 0);
  const totalDias   = meses.reduce((s, m) => s + m.diasConStock, 0);
  if (totalDias === 0) return '—';
  return (totalVentas / totalDias).toFixed(4);
}

function Leyenda() {
  return (
    <div className="planilla-leyenda">
      <span className="planilla-leyenda-titulo">Estado mensual:</span>
      <span className="planilla-leyenda-item planilla-leyenda-normal">Normal (≥90% días con stock)</span>
      <span className="planilla-leyenda-item planilla-leyenda-quiebre">Quiebre parcial</span>
      <span className="planilla-leyenda-item planilla-leyenda-sinstock">Sin stock (mes completo)</span>
    </div>
  );
}

type Props = {
  params: PlanillaVentasParams;
  onPageChange: (page: number) => void;
};

export default function PlanillaTable({ params, onPageChange }: Props) {
  const { data, isLoading, isFetching, isError } = usePlanillaVentas(params);

  const items      = data?.items ?? [];
  const total      = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / params.pageSize));
  const mesHeaders: { year: number; month: number }[] = items[0]?.meses ?? [];

  // total columns: SKU+Desc, Género, Stock mín., [13 months], Rot.DesEstac., DDSTK
  const FIXED_COLS  = 3;
  const SUMM_COLS   = 2;
  const totalCols   = FIXED_COLS + mesHeaders.length + SUMM_COLS;

  return (
    <section className="card table-card">
      <Leyenda />

      <div className="table-wrap" style={{ overflowX: 'auto' }}>
        <table className="table planilla-tabla">
          <thead>
            <tr>
              <th className="planilla-sticky-col planilla-col-sku"
                  title="Código de artículo y descripción">
                SKU / Descripción
              </th>
              <th title="Género del artículo según el catálogo">Género</th>
              <th className="planilla-col-stock"
                  title="Stock mínimo configurado para el artículo">
                Stock mín.
              </th>

              {isLoading
                ? Array.from({ length: 13 }).map((_, i) => (
                    <th key={i}><span className="skeleton skel-40" /></th>
                  ))
                : mesHeaders.map((m, idx) => {
                    const esReferencia = idx === mesHeaders.length - 1;
                    return (
                      <th
                        key={`${m.year}-${m.month}`}
                        className="planilla-col-mes"
                        title={
                          esReferencia
                            ? `${mesLabel(m.year, m.month)} — Mes de referencia (no entra en el promedio de Rot. DesEstac.)\nFórmula: ventas ÷ días con stock\nAmarillo = quiebre parcial · Gris = sin stock`
                            : `${mesLabel(m.year, m.month)} — Rotación diaria real del mes\nFórmula: ventas_mes ÷ días_con_stock\nAmarillo = quiebre parcial · Gris = sin stock`
                        }
                        style={esReferencia ? { opacity: 0.65, fontStyle: 'italic' } : undefined}
                      >
                        {mesLabel(m.year, m.month)}
                      </th>
                    );
                  })}

              <th className="planilla-col-summary"
                  title={
                    'Rotación Diaria Desestacionalizada (promedio)\n' +
                    'Promedio de la rotación diaria real en meses sin quiebre de stock (≥90% días con stock),\n' +
                    'excluyendo el mes de referencia más reciente.\n' +
                    'Fórmula: AVG(ventas_mes ÷ días_con_stock) donde estado_mes = normal\n' +
                    'Nota: en Fase 2 se aplicará el factor estacional del SOAP para la versión definitiva.'
                  }>
                Rot. DesEstac.
              </th>
              <th className="planilla-col-summary"
                  title={
                    'Demanda Diaria con Stock (DDSTK)\n' +
                    'Fórmula: Σ ventas del período ÷ Σ días con stock del período\n' +
                    'Representa la tasa de venta diaria histórica promedio del artículo,\n' +
                    'calculada sobre todos los meses de la ventana de 13 meses.'
                  }>
                DDSTK
              </th>
            </tr>
          </thead>

          <tbody>
            {isLoading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i}>
                  <td className="planilla-sticky-col"><span className="skeleton skel-120" /></td>
                  <td><span className="skeleton skel-80" /></td>
                  <td><span className="skeleton skel-40" /></td>
                  {Array.from({ length: 13 }).map((__, j) => (
                    <td key={j}><span className="skeleton skel-40" /></td>
                  ))}
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
                const rotDesEstac = calcRotDesEstac(row.meses);
                const ddstk       = calcDdstk(row.meses);
                return (
                  <tr key={row.sku}>
                    <td className="planilla-sticky-col planilla-col-sku">
                      <span className="planilla-sku">{row.sku}</span>
                      <span className="planilla-desc">{row.descripcion ?? '—'}</span>
                    </td>
                    <td>{row.generoDescripcion ?? '—'}</td>
                    <td className="planilla-col-stock">{row.stockMinimo ?? '—'}</td>

                    {row.meses.map(mes => (
                      <td
                        key={`${mes.year}-${mes.month}`}
                        className="planilla-col-mes"
                        style={{ backgroundColor: estadoMesBg(mes.estadoMes) }}
                        title={`${mesLabel(mes.year, mes.month)} · ${mes.diasConStock}/${mes.diasNaturalesMes} días con stock · ${mes.ventasCantidad} uds.`}
                      >
                        {mes.rotacionDiariaReal != null
                          ? mes.rotacionDiariaReal.toFixed(4)
                          : '0.0000'}
                      </td>
                    ))}

                    <td className={`planilla-col-summary${rotDesEstac === '—' ? ' sin-datos' : ''}`}>
                      {rotDesEstac}
                    </td>
                    <td className={`planilla-col-summary${ddstk === '—' ? ' sin-datos' : ''}`}>
                      {ddstk}
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
