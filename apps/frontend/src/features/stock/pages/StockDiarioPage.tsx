import { useEffect, useMemo, useRef, useState } from 'react';
import api from '../../../api/client';
import '../../../styles/dark-layout.css';

type Row = Record<string, unknown>;

export default function StockDiarioPage() {
  const [skuInput,   setSkuInput]   = useState('');
  const [yearInput,  setYearInput]  = useState('');
  const [monthInput, setMonthInput] = useState('');
  const [sku,   setSku]   = useState('');
  const [year,  setYear]  = useState('');
  const [month, setMonth] = useState('');
  const [items, setItems] = useState<Row[]>([]);
  const [page,     setPage]     = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total,    setTotal]    = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  const filterRef = useRef<HTMLElement | null>(null);
  const tableRef  = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const els = [filterRef.current, tableRef.current].filter(Boolean) as HTMLElement[];
    const obs = new IntersectionObserver(
      entries => entries.forEach(e => { if (e.isIntersecting) { (e.target as HTMLElement).classList.add('visible'); obs.unobserve(e.target); } }),
      { threshold: 0.04 }
    );
    els.forEach(el => obs.observe(el));
    return () => obs.disconnect();
  }, []);

  const fetchPage = async (pn: number, f: { sku: string; year: string; month: string }, ps = pageSize) => {
    setIsLoading(true);
    try {
      const params: Record<string, unknown> = { page: pn, pageSize: ps };
      if (f.sku.trim()) params.sku  = f.sku.trim().toUpperCase();
      if (f.year)       params.year = Number(f.year);
      if (f.month)      params.month = Number(f.month);
      const res  = await api.get('/api/StockDiario/raw', { params });
      const data = res.data as Row;
      const out  = (data['items'] ?? data['Items'] ?? data) as unknown;
      const rows = Array.isArray(out) ? (out as Row[]) : [];
      setItems(rows);
      setTotal(Number(data['total'] ?? data['Total'] ?? rows.length));
    } catch { setItems([]); setTotal(0); }
    finally  { setIsLoading(false); }
  };

  useEffect(() => { fetchPage(page, { sku, year, month }, pageSize); }, [page, sku, year, month, pageSize]);

  const handleSearch = () => { setSku(skuInput); setYear(yearInput); setMonth(monthInput); setPage(1); };
  const handleReset  = () => { setSkuInput(''); setYearInput(''); setMonthInput(''); setSku(''); setYear(''); setMonth(''); setPage(1); };
  const totalPages = useMemo(() => Math.max(1, Math.ceil((total || 0) / pageSize)), [total, pageSize]);

  return (
    <div className="pg-page">

      <section className="pg-hero">
        <div className="pg-hero-grid" />
        <div className="pg-hero-glow" />
        <div className="pg-hero-content">
          <h1 className="pg-title">Stock Diario</h1>
          <p className="pg-subtitle">Inventario diario por producto y depósito.</p>
          {total > 0 && <div className="pg-stat-pill">{total.toLocaleString('es-UY')} registros</div>}
        </div>
      </section>

      <div className="pg-container">

        <section className="pg-filter-card pg-reveal" ref={filterRef}>
          <div className="pg-filters-grid">
            <div className="pg-form-row">
              <label className="pg-label">SKU</label>
              <input className="pg-input" placeholder="ej. I01497" value={skuInput}
                onChange={e => setSkuInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()} />
            </div>
            <div className="pg-form-row">
              <label className="pg-label">Año</label>
              <input className="pg-input" type="number" placeholder="ej. 2024" value={yearInput}
                onChange={e => setYearInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()} />
            </div>
            <div className="pg-form-row">
              <label className="pg-label">Mes</label>
              <input className="pg-input" type="number" placeholder="1 – 12" value={monthInput}
                onChange={e => setMonthInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()} />
            </div>
          </div>
          <div className="pg-filter-actions">
            <button type="button" className="pg-btn" onClick={handleSearch}>Buscar</button>
            <button type="button" className="pg-btn-ghost" onClick={handleReset}>Limpiar</button>
          </div>
        </section>

        <section className="pg-table-card pg-reveal" ref={tableRef}>
          <div className="pg-table-wrap">
            <table className="pg-table">
              <thead>
                <tr>
                  <th className="pg-th-key">SKU</th>
                  <th>Fecha</th>
                  <th>Cantidad</th>
                  <th>Depósito</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  Array.from({ length: 10 }).map((_, i) => (
                    <tr key={i}>
                      <td><span className="pg-skeleton pg-skeleton-sm" /></td>
                      {Array.from({ length: 3 }).map((__, j) => <td key={j}><span className="pg-skeleton pg-skeleton-md" /></td>)}
                    </tr>
                  ))
                ) : items.length === 0 ? (
                  <tr><td colSpan={4} className="pg-empty">No hay resultados.</td></tr>
                ) : (
                  items.map((r, i) => (
                    <tr key={String(r['id'] ?? r['Id'] ?? i)}>
                      <td className="pg-td-key">{String(r['sku'] ?? r['Sku'] ?? '')}</td>
                      <td>{String(r['fecha'] ?? r['Fecha'] ?? '')}</td>
                      <td>{String(r['cantidad'] ?? r['Cantidad'] ?? r['CantidadTotal'] ?? '')}</td>
                      <td>
                        {(r['depositoId'] ?? r['DepositoId'])
                          ? <span className="pg-badge">{String(r['depositoId'] ?? r['DepositoId'])}</span>
                          : '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="pg-pager">
            <span className="pg-pager-info">Página <strong>{page}</strong> de <strong>{totalPages}</strong> — Total: <strong>{total}</strong></span>
            <div className="pg-pager-right">
              <select className="pg-page-size-select" value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}>
                {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n} filas</option>)}
              </select>
              <button className="pg-pager-btn" disabled={page <= 1}          onClick={() => setPage(p => p - 1)}>Anterior</button>
              <button className="pg-pager-btn" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Siguiente</button>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}
