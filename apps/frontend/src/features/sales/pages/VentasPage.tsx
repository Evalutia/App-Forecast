import { useState } from "react";
import type { VentasQuery } from "../../sales/types/ventas";
import FiltrosVentas from "../../sales/components/FiltrosVentas";
import TablaVentas from "../../sales/components/TablaVentas";
import BackToDashboardButton from "../../users/components/BackToDashboardButton";
import ScrollToTopButton from "../../users/components/ScrollToTopButton";

export default function VentasPage() {
  const [query, setQuery] = useState<VentasQuery>({ page: 1, pageSize: 20 });

  const handleApply = (q: VentasQuery) => setQuery(q);
  const handleClear = () => setQuery({ page: 1, pageSize: 20 });
  const handlePageChange = (page: number) => setQuery((prev) => ({ ...prev, page }));
  const handlePageSizeChange = (pageSize: number) => setQuery((prev) => ({ ...prev, pageSize, page: 1 }));

  return (
    <div className="ventas-page">
      <div className="ventas-header">
        <a href="/home" className="ventas-brand">Evalutia</a>

        <div className="ventas-actions">
          <BackToDashboardButton />
        </div>
      </div>

      <div className="ventas-container">
        <header className="section-head">
          <h1 className="section-title">Ventas</h1>
          <p className="section-subtitle">Explorá el historial de ventas en detalle.</p>
        </header>

        <FiltrosVentas initial={query} onApply={handleApply} onClear={handleClear} />

        <div style={{ marginTop: "1rem", width: "100%" }}>
          <TablaVentas query={query} onPageChange={handlePageChange} onPageSizeChange={handlePageSizeChange} />
        </div>
      </div>
      <ScrollToTopButton />
    </div>
  );
}
