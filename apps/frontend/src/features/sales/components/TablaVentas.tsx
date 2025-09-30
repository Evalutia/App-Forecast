import { useMemo } from "react";
import type { VentasQuery } from "../types/ventas";
import type { Venta } from "../types/ventas";
import { useVentasDetalle, selectDetalleRows, getPaging } from "../hooks/useVentas";

type Props = {
  query: VentasQuery;
  onPageChange: (page: number) => void;
  onRowClick?: (venta: Venta) => void;
};

export default function TablaVentas({ query, onPageChange, onRowClick }: Props) {
  const { data, isLoading, isFetching, isError, error } = useVentasDetalle(query, {
    enabled: !query.agregado,
  });

  const rows = useMemo(() => selectDetalleRows(data), [data]);
  const paging = useMemo(() => getPaging(data), [data]);
  const totalPages = useMemo(
    () => Math.max(1, Math.ceil((paging.total || 0) / (query.pageSize || 50))),
    [paging.total, query.pageSize]
  );

  if (isError) {
    return <div className="alert">Ocurrió un error al cargar ventas. {(error as any)?.message ?? ""}</div>;
  }

  return (
    <section className="card table-card">
      <div style={{ marginBottom: ".5rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div className="muted">{isFetching ? "Actualizando..." : "Listado de ventas (detalle)"}</div>
        <div className="muted">Total: <strong>{paging.total}</strong></div>
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>SKU</th>
              <th>Cantidad</th>
              <th>Fuente</th>
              <th>ID</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i}>
                  <td><span className="skeleton skel-20" /></td>
                  <td><span className="skeleton skel-28" /></td>
                  <td><span className="skeleton skel-12" /></td>
                  <td><span className="skeleton skel-24" /></td>
                  <td><span className="skeleton skel-10" /></td>
                </tr>
              ))
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="muted" style={{ textAlign: "center", padding: "1.2rem 0" }}>
                  No hay resultados para los filtros aplicados.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr
                  key={r.id}
                  style={onRowClick ? { cursor: "pointer" } : undefined}
                  onClick={() => onRowClick?.(r)}
                >
                  <td>{r.fecha}</td>
                  <td className="mono">{r.sku}</td>
                  <td>{r.cantidad}</td>
                  <td>{r.fuente || "-"}</td>
                  <td className="muted">{r.id}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="pager">
        <div>Página {paging.page} de {totalPages}</div>
        <div className="pager-buttons">
          <button
            className="pager-btn"
            disabled={paging.page <= 1}
            onClick={() => onPageChange(paging.page - 1)}
          >
            Anterior
          </button>
          <button
            className="pager-btn"
            disabled={paging.page >= totalPages}
            onClick={() => onPageChange(paging.page + 1)}
          >
            Siguiente
          </button>
        </div>
      </div>
    </section>
  );
}
