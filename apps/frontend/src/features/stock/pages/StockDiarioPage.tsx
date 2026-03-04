import { useState } from 'react';
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

  const handleSearch = async () => {
    if (!sku || !year || !month) return;
    setIsLoading(true);
    try {
      const res = await api.get('/api/StockDiario', { params: { sku, year, month, page, pageSize } });
      const data = res.data;
      const out = data.items ?? data.Items ?? data;
      setItems(out);
      setTotal(data.total ?? data.Total ?? out.length);
    } catch (e) {
      setItems([]);
      setTotal(0);
    } finally {
      setIsLoading(false);
    }
  };

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
          <button className="btn" onClick={() => { setPage(1); handleSearch(); }}>Buscar</button>
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Cantidad</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>{Array.from({ length: 2 }).map((__, j) => <td key={j}><span className="skeleton skel-20"/></td>)}</tr>
                ))
              ) : items.length === 0 ? (
                <tr><td colSpan={2} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>No hay resultados.</td></tr>
              ) : (
                items.map((r: any, i: number) => (
                  <tr key={i}>
                    <td>{r.fecha ?? r.Fecha}</td>
                    <td>{r.cantidad ?? r.CantidadTotal}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="pager" style={{ marginTop: '0.6rem' }}>
          <div>Página {page} de {Math.max(1, Math.ceil((total || 0) / pageSize))} — Total: <strong>{total}</strong></div>
          <div className="pager-buttons">
            <button className="pager-btn" disabled={page <= 1} onClick={() => { setPage(page - 1); handleSearch(); }}>Anterior</button>
            <button className="pager-btn" disabled={page >= Math.max(1, Math.ceil((total || 0) / pageSize))} onClick={() => { setPage(page + 1); handleSearch(); }}>Siguiente</button>
          </div>
        </div>
      </div>
    </div>
    </>
  );
}
