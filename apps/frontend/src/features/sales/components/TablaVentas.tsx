import { useMemo } from "react";
import type { VentasQuery, Venta } from "../types/ventas";
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
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Ocurrió un error al cargar ventas. {(error as any)?.message ?? ""}
      </div>
    );
  }

  return (
    <div className="w-full rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm text-gray-600">
          {isFetching ? "Actualizando..." : "Listado de ventas (detalle)"}
        </div>
        <div className="text-xs text-gray-500">
          Total: <span className="font-semibold">{paging.total}</span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="sticky top-0 bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-3 py-2">Fecha</th>
              <th className="px-3 py-2">SKU</th>
              <th className="px-3 py-2">Cantidad</th>
              <th className="px-3 py-2">Fuente</th>
              <th className="px-3 py-2">ID</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td className="px-3 py-2">
                    <div className="h-3 w-20 rounded bg-gray-200" />
                  </td>
                  <td className="px-3 py-2">
                    <div className="h-3 w-24 rounded bg-gray-200" />
                  </td>
                  <td className="px-3 py-2">
                    <div className="h-3 w-12 rounded bg-gray-200" />
                  </td>
                  <td className="px-3 py-2">
                    <div className="h-3 w-24 rounded bg-gray-200" />
                  </td>
                  <td className="px-3 py-2">
                    <div className="h-3 w-10 rounded bg-gray-200" />
                  </td>
                </tr>
              ))
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-sm text-gray-500">
                  No hay resultados para los filtros aplicados.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr
                  key={r.id}
                  className={onRowClick ? "cursor-pointer hover:bg-gray-50" : ""}
                  onClick={() => onRowClick?.(r)}
                >
                  <td className="px-3 py-2">{r.fecha}</td>
                  <td className="px-3 py-2 font-mono">{r.sku}</td>
                  <td className="px-3 py-2">{r.cantidad}</td>
                  <td className="px-3 py-2">{r.fuente || "-"}</td>
                  <td className="px-3 py-2 text-gray-500">{r.id}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Paginación */}
      <div className="mt-4 flex items-center justify-between">
        <div className="text-xs text-gray-500">
          Página {paging.page} de {totalPages}
        </div>
        <div className="flex items-center gap-2">
          <button
            className="rounded-lg border px-3 py-1 text-sm disabled:opacity-50"
            disabled={paging.page <= 1}
            onClick={() => onPageChange(paging.page - 1)}
          >
            Anterior
          </button>
          <button
            className="rounded-lg border px-3 py-1 text-sm disabled:opacity-50"
            disabled={paging.page >= totalPages}
            onClick={() => onPageChange(paging.page + 1)}
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>
  );
}
