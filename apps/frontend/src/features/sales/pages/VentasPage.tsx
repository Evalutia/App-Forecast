import { useEffect, useRef, useState } from 'react';
import type { VentasQuery } from '../../sales/types/ventas';
import FiltrosVentas from '../../sales/components/FiltrosVentas';
import TablaVentas from '../../sales/components/TablaVentas';
import '../../../styles/dark-layout.css';

export default function VentasPage() {
  const [query, setQuery] = useState<VentasQuery>({ page: 1, pageSize: 20 });

  const contentRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      entries => entries.forEach(e => { if (e.isIntersecting) { (e.target as HTMLElement).classList.add('visible'); obs.unobserve(e.target); } }),
      { threshold: 0.04 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const handleApply          = (q: VentasQuery) => setQuery(q);
  const handleClear          = ()               => setQuery({ page: 1, pageSize: 20 });
  const handlePageChange     = (page: number)   => setQuery(prev => ({ ...prev, page }));
  const handlePageSizeChange = (ps: number)     => setQuery(prev => ({ ...prev, pageSize: ps, page: 1 }));

  return (
    <div className="pg-page">

      <section className="pg-hero">
        <div className="pg-hero-grid" />
        <div className="pg-hero-glow" />
        <div className="pg-hero-content">
          <h1 className="pg-title">Ventas</h1>
          <p className="pg-subtitle">Historial detallado de ventas históricas.</p>
        </div>
      </section>

      <div className="pg-container pg-container--wide">
        <div className="pg-reveal" ref={contentRef}>
          <FiltrosVentas initial={query} onApply={handleApply} onClear={handleClear} />
          <div style={{ marginTop: '1rem' }}>
            <TablaVentas query={query} onPageChange={handlePageChange} onPageSizeChange={handlePageSizeChange} />
          </div>
        </div>
      </div>

    </div>
  );
}
