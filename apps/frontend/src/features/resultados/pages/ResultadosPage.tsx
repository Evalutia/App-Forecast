import BackToDashboardButton from '../../users/components/BackToDashboardButton';
import ScrollToTopButton from '../../users/components/ScrollToTopButton';
import ResumenCards from '../components/ResumenCards';
import StockAnalysisTable from '../components/StockAnalysisTable';
import TopVentasPerdidasChart from '../components/charts/TopVentasPerdidasChart';
import StockoutDistributionChart from '../components/charts/StockoutDistributionChart';
import AbcChart from '../components/charts/AbcChart';
import VentasTrendChart from '../components/charts/VentasTrendChart';

export default function ResultadosPage() {
  return (
    <div className="predicciones-page">
      <div className="predicciones-header">
        <a href="/home" className="predicciones-brand">Evalutia</a>
        <div className="predicciones-actions">
          <BackToDashboardButton />
        </div>
      </div>

      <div className="predicciones-container">
        <header className="section-head">
          <h1 className="section-title">Resultados</h1>
          <p className="section-subtitle">
            Análisis de stock, ventas perdidas por quiebre y sugerencia de compra por producto.
          </p>
        </header>

        <h2 className="subsection-title">Resumen general</h2>
        <ResumenCards />

        <div className="section-divider"></div>

        <h2 className="subsection-title">Gráficos de análisis</h2>
        <p className="section-subtitle" style={{ marginBottom: '1rem' }}>
          Visualizaciones clave para tomar decisiones de compra con datos.
        </p>

        <div className="charts-grid">
          <VentasTrendChart />
          <TopVentasPerdidasChart />
          <AbcChart />
          <StockoutDistributionChart />
        </div>

        <div className="section-divider"></div>

        <h2 className="subsection-title">Análisis por SKU</h2>
        <p className="section-subtitle" style={{ marginBottom: '1rem' }}>
          Hacé clic en una fila para ver el detalle completo del producto.
        </p>
        <StockAnalysisTable />
      </div>

      <ScrollToTopButton />
    </div>
  );
}
