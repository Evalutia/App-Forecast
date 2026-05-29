import type { PlanillaVentasDto, PlanillaVentasParams } from '../types/planilla';
import { usePlanillaVentas } from '../hooks/usePlanilla';

const MESES_CORTOS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];

function mesLabel(year: number, month: number): string {
  return `${MESES_CORTOS[month - 1]} ${String(year).slice(2)}`;
}

function estadoMesBg(estado: string): string {
  if (estado === 'normal') return 'rgba(22,163,74,0.12)';
  if (estado === 'quiebre_parcial') return 'rgba(217,119,6,0.13)';
  if (estado === 'sin_stock') return 'rgba(220,38,38,0.12)';
  return '';
}

function MesLeyenda() {
  return (
    <div className="planilla-leyenda">
      <span className="planilla-leyenda-titulo">Estado de stock por mes:</span>
      <span className="planilla-leyenda-item planilla-leyenda-normal">Normal (≥90% días con stock)</span>
      <span className="planilla-leyenda-item planilla-leyenda-quiebre">Quiebre parcial (1–89%)</span>
      <span className="planilla-leyenda-item planilla-leyenda-sinstock">Sin stock (0 días)</span>
    </div>
  );
}

type Props = {
  params: PlanillaVentasParams;
  onPageChange: (page: number) => void;
};

export default function PlanillaTable({ params, onPageChange }: Props) {
  const { data, isLoading, isFetching, isError } = usePlanillaVentas(params);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / params.pageSize));

  // Encabezados de mes: tomados del primer SKU si hay datos, si no se generan vacíos
  const mesHeaders: { year: number; month: number }[] = items[0]?.meses ?? [];

  return (
    <section className="card table-card">
      <MesLeyenda />

      <div className="table-wrap" style={{ overflowX: 'auto' }}>
        <table className="table planilla-tabla">
          <thead>
            <tr>
              <th className="planilla-sticky-col planilla-col-sku">SKU / Descripción</th>
              <th>Marca</th>
              <th className="planilla-col-stock">Stock mín.</th>
              {isLoading
                ? Array.from({ length: 13 }).map((_, i) => (
                    <th key={i}><span className="skeleton skel-40" /></th>
                  ))
                : mesHeaders.map(m => (
                    <th key={`${m.year}-${m.month}`} className="planilla-col-mes">
                      {mesLabel(m.year, m.month)}
                    </th>
                  ))
              }
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
                </tr>
              ))
            ) : isError ? (
              <tr>
                <td colSpan={3 + mesHeaders.length} className="muted" style={{ textAlign: 'center', padding: '1.5rem 0' }}>
                  No se pudo cargar la planilla.
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={3 + mesHeaders.length} className="muted" style={{ textAlign: 'center', padding: '1.5rem 0' }}>
                  No se encontraron artículos con los filtros aplicados.
                </td>
              </tr>
            ) : (
              items.map((row: PlanillaVentasDto) => (
                <tr key={row.sku}>
                  <td className="planilla-sticky-col planilla-col-sku">
                    <span className="planilla-sku">{row.sku}</span>
                    <span className="planilla-desc">{row.descripcion ?? '—'}</span>
                  </td>
                  <td>{row.marcaNombre ?? '—'}</td>
                  <td className="planilla-col-stock">{row.stockMinimo ?? '—'}</td>
                  {row.meses.map(mes => (
                    <td
                      key={`${mes.year}-${mes.month}`}
                      className="planilla-col-mes"
                      style={{ backgroundColor: estadoMesBg(mes.estadoMes) }}
                      title={`${mesLabel(mes.year, mes.month)} · ${mes.diasConStock}/${mes.diasNaturalesMes} días con stock`}
                    >
                      {mes.ventasCantidad.toLocaleString('es-AR')}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="pager">
        <div className="muted">
          {isFetching && !isLoading ? 'Actualizando…' : `${total} artículos · Página ${params.page} de ${totalPages}`}
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
