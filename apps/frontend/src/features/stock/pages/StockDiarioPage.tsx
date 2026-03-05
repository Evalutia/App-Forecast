import { useEffect, useMemo, useState } from 'react';
import api from '../../../api/client';

export default function StockDiarioPage() {
  const [sku, setSku] = useState('');
  const [year, setYear] = useState<number | undefined>(undefined);
  const [month, setMonth] = useState<number | undefined>(undefined);
  const [items, setItems] = useState<any[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  const fetchPage = async () => {
    setIsLoading(true);
    try {
      const params: any = { page, pageSize };
      if (sku && String(sku).trim() !== '') params.sku = String(sku).trim().toUpperCase();
      if (year) params.year = year;
      if (month) params.month = month;

      const res = await api.get('/api/StockDiario/raw', { params });
      const data = res.data;
      const out = data.items ?? data.Items ?? data;
      setItems(out);
      setTotal(data.total ?? data.Total ?? out.length);
    } catch {
      setItems([]);
      setTotal(0);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { fetchPage(); }, [page]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil((total || 0) / pageSize)), [total, pageSize]);

  return (
    <>
      <div className="stock-topbar-wide">
        <div className="home-header">
          <a href="/home" className="home-brand">EVALUTIA</a>
          <div className="home-actions">
            <a href="/home" className="btn btn--sm">← Volver al dashboard</a>
          </div>
        </div>
      </div>

      <div className="stock-page">
        <div className="stock-container">
        <header className="section-head">
          <h1 className="section-title">Stock diario</h1>
          <p className="section-subtitle">Suma diaria de stock para un SKU y mes.</p>
        </header>

        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          <input placeholder="SKU" value={sku} onChange={e => setSku(e.target.value)} />
          <input placeholder="Año" type="number" onChange={e => setYear(Number(e.target.value) || undefined)} />
          <input placeholder="Mes" type="number" onChange={e => setMonth(Number(e.target.value) || undefined)} />
          <button className="btn" onClick={() => { setPage(1); fetchPage(); }}>Buscar</button>
        </div>

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
                  <tr key={i}>{Array.from({ length: 4 }).map((__, j) => <td key={j}><span className="skeleton skel-20"/></td>)}</tr>
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

        <div className="pager" style={{ marginTop: '0.6rem' }}>
          <div>Página {page} de {totalPages} — Total: <strong>{total}</strong></div>
          <div className="pager-buttons">
            <button className="pager-btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</button>
            <button className="pager-btn" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Siguiente</button>
          </div>
        </div>
      </div>
    </div>
    </>
  );
}
