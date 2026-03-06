import { useEffect, useMemo, useState } from 'react';
import api from '../../../api/client';
import BackToDashboardButton from '../../users/components/BackToDashboardButton';
import ScrollToTopButton from '../../users/components/ScrollToTopButton';

export default function StockDiarioPage() {
  const [skuInput, setSkuInput] = useState('');
  const [yearInput, setYearInput] = useState('');
  const [monthInput, setMonthInput] = useState('');
  const [sku, setSku] = useState('');
  const [year, setYear] = useState('');
  const [month, setMonth] = useState('');
  const [items, setItems] = useState<any[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  const fetchPage = async (pageNum: number, filters: { sku: string; year: string; month: string }, ps = pageSize) => {
    setIsLoading(true);
    try {
      const params: any = { page: pageNum, pageSize: ps };
      if (filters.sku && filters.sku.trim() !== '') params.sku = filters.sku.trim().toUpperCase();
      if (filters.year) params.year = Number(filters.year);
      if (filters.month) params.month = Number(filters.month);
      const res = await api.get('/api/StockDiario/raw', { params });
      const data = res.data;
      const out = data.items ?? data.Items ?? data;
      setItems(Array.isArray(out) ? out : []);
      setTotal(data.total ?? data.Total ?? (Array.isArray(out) ? out.length : 0));
    } catch {
      setItems([]);
      setTotal(0);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { fetchPage(page, { sku, year, month }, pageSize); }, [page, sku, year, month, pageSize]);

  const handleSearch = () => {
    setSku(skuInput);
    setYear(yearInput);
    setMonth(monthInput);
    setPage(1);
  };

  const handleReset = () => {
    setSkuInput(''); setYearInput(''); setMonthInput('');
    setSku(''); setYear(''); setMonth('');
    setPage(1);
  };

  const totalPages = useMemo(() => Math.max(1, Math.ceil((total || 0) / pageSize)), [total, pageSize]);

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
          <h1 className="section-title">Stock diario</h1>
          <p className="section-subtitle">Suma diaria de stock para un SKU y mes.</p>
        </header>

        <section className="card filters-card predicciones-filtros">
          <div className="filters-grid">
            <div className="form-row">
              <label className="label">SKU</label>
              <input
                className="input"
                placeholder="p.ej. I01497"
                value={skuInput}
                onChange={e => setSkuInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <div className="form-row">
              <label className="label">Año</label>
              <input
                className="input"
                type="number"
                placeholder="p.ej. 2024"
                value={yearInput}
                onChange={e => setYearInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <div className="form-row">
              <label className="label">Mes</label>
              <input
                className="input"
                type="number"
                placeholder="1 – 12"
                value={monthInput}
                onChange={e => setMonthInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
            </div>
          </div>
          <div className="filters-actions">
            <button type="button" className="button" onClick={handleSearch}>Aplicar filtros</button>
            <button type="button" className="button button-ghost" onClick={handleReset}>Limpiar</button>
          </div>
        </section>

        <section className="card table-card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Fecha</th>
                  <th>Cantidad</th>
                  <th>Depósito</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i}>{Array.from({ length: 4 }).map((__, j) => <td key={j}><span className="skeleton skel-20" /></td>)}</tr>
                  ))
                ) : items.length === 0 ? (
                  <tr><td colSpan={4} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>No hay resultados.</td></tr>
                ) : (
                  items.map((r: any, i: number) => (
                    <tr key={r.id ?? r.Id ?? i}>
                      <td className="mono">{r.sku ?? r.Sku}</td>
                      <td>{r.fecha ?? r.Fecha}</td>
                      <td>{r.cantidad ?? r.Cantidad ?? r.CantidadTotal}</td>
                      <td>{r.depositoId ?? r.DepositoId}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="pager">
            <div>Página {page} de {totalPages} — Total: <strong>{total}</strong></div>
            <div className="pager-buttons">
              <button className="pager-btn" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Anterior</button>
              <button className="pager-btn" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Siguiente</button>
            </div>
          </div>
          <div style={{ marginTop: '.5rem' }} className="muted">
            Filas por página:&nbsp;
            <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
              {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
        </section>
      </div>
      <ScrollToTopButton />
    </div>
  );
}
