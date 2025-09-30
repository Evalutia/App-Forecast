import { useState } from "react";
import type { VentasQuery } from "../../sales/types/ventas";
import FiltrosVentas from "../../sales/components/FiltrosVentas";
import TablaVentas from "../../sales/components/TablaVentas";
import BackToDashboardButton from '../../users/components/BackToDashboardButton';

export default function VentasPage() {
  const [query, setQuery] = useState<VentasQuery>({
    page: 1,
    pageSize: 50,
  });

  const handleApply = (q: VentasQuery) => setQuery(q);
  const handleClear = () =>
    setQuery({
      page: 1,
      pageSize: 50,
    });
  const handlePageChange = (page: number) => setQuery((prev) => ({ ...prev, page }));

  return (
    <div className="mx-auto max-w-7xl p-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
            <span className="text-sm text-emerald-100/80">Evalutia</span>
            <BackToDashboardButton />
        </div>
        <div className="mb-4">
            <h1 className="text-xl font-semibold">Ventas</h1>
            <p className="text-sm text-gray-600">
            Explorá el historial de ventas en detalle.
            </p>
        </div>

        <FiltrosVentas initial={query} onApply={handleApply} onClear={handleClear} />

        <div className="mt-4">
            <TablaVentas query={query} onPageChange={handlePageChange} />
        </div>
    </div>
  );
}
