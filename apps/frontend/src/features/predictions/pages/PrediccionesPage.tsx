import { useEffect, useRef } from 'react';
import PrediccionesFilters from '../components/PrediccionesFilters';
import PrediccionesTable from '../components/PrediccionesTable';
import DatosExtra from '../components/DatosExtra';
import TopSkusVentasTable from '../components/TopSkusVentasTable';
import '../../../styles/dark-layout.css';

export default function PrediccionesPage() {
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
          <h1 className="pg-title">Predicciones</h1>
          <p className="pg-subtitle">
            Consultá el top de SKUs, explorá el resumen por producto y revisá el historial de predicciones.
          </p>
        </div>
      </section>

      <div className="pg-container pg-container--wide">
        <div className="pg-reveal" ref={contentRef}>

          <h2 className="pg-subsection-title">Top 20 productos más vendidos (últimos 12 meses)</h2>
          <TopSkusVentasTable />

          <h2 className="pg-subsection-title">Resumen y proyección por SKU</h2>
          <DatosExtra />

          <h2 className="pg-subsection-title">Historial de predicciones</h2>
          <PrediccionesFilters />
          <PrediccionesTable />

        </div>
      </div>

    </div>
  );
}
