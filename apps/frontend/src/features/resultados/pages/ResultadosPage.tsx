import { useEffect, useRef } from 'react';
import ResumenCards from '../components/ResumenCards';
import StockAnalysisTable from '../components/StockAnalysisTable';
import TopVentasPerdidasChart from '../components/charts/TopVentasPerdidasChart';
import StockoutDistributionChart from '../components/charts/StockoutDistributionChart';
import AbcChart from '../components/charts/AbcChart';
import VentasTrendChart from '../components/charts/VentasTrendChart';
import '../../../styles/dark-layout.css';

export default function ResultadosPage() {
  const contentRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      entries => entries.forEach(e => {
        if (e.isIntersecting) { (e.target as HTMLElement).classList.add('visible'); obs.unobserve(e.target); }
      }),
      { threshold: 0.02 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div className="pg-page">

      <section className="pg-hero">
        <div className="pg-hero-grid" />
        <div className="pg-hero-glow" />
        <div className="pg-hero-content">
          <h1 className="pg-title">Resultados</h1>
          <p className="pg-subtitle">
            Análisis ABC, tasa de stockout y ventas perdidas estimadas por producto.
          </p>
        </div>
      </section>

      <div className="pg-container pg-container--wide">
        <div className="pg-reveal" ref={contentRef}>

          <h2 className="pg-subsection-title">Resumen general</h2>
          <ResumenCards />

          <h2 className="pg-subsection-title">Gráficos de análisis</h2>
          <div className="pg-charts-grid">
            <VentasTrendChart />
            <TopVentasPerdidasChart />
            <AbcChart />
            <StockoutDistributionChart />
          </div>

          <h2 className="pg-subsection-title">Análisis por SKU</h2>
          <p className="pg-subtitle" style={{ textAlign: 'left', marginBottom: '12px' }}>
            Hacé clic en una fila para ver el detalle completo del producto.
          </p>
          <StockAnalysisTable />

        </div>
      </div>

    </div>
  );
}
