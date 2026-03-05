import { useEffect, useMemo, useState } from 'react';
import api from '../../../api/client';

export default function ArticulosPage() {
  const [sku, setSku] = useState('');
  const [items, setItems] = useState<any[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(100);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  const fetchPage = async () => {
    setIsLoading(true);
    try {
      const params: any = { page, pageSize };
      if (sku && String(sku).trim() !== '') params.sku = String(sku).trim();
      const res = await api.get('/api/Articulos', { params });
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

  useEffect(() => { fetchPage(); }, [page]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil((total || 0) / pageSize)), [total, pageSize]);

  const cols = 19;

  return (
    <>
      <div className="articulos-topbar-wide">
        <div className="home-header">
          <a href="/home" className="home-brand">EVALUTIA</a>
          <div className="home-actions">
            <a href="/home" className="btn btn--sm">← Volver al dashboard</a>
          </div>
        </div>
      </div>

      <div className="articulos-page">
        <div className="articulos-container">
        <header className="section-head">
          <h1 className="section-title">Artículos</h1>
          <p className="section-subtitle">Listado de artículos cargados en la base de datos.</p>
        </header>

        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          <input placeholder="SKU" value={sku} onChange={e => setSku(e.target.value)} />
          <button className="btn" onClick={() => { setPage(1); fetchPage(); }}>Buscar</button>
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Descripción</th>
                <th>Familia ID</th>
                <th>Familia</th>
                <th>Género ID</th>
                <th>Género</th>
                <th>Sección ID</th>
                <th>Sección</th>
                <th>Marca ID</th>
                <th>Marca</th>
                <th>Temporada ID</th>
                <th>Temporada</th>
                <th>Fec. Alta</th>
                <th>Fec. Modif.</th>
                <th>Comentario</th>
                <th>Fact Desc Min</th>
                <th>Fact Desc Max</th>
                <th>Desc Válida</th>
                <th>Stock Mínimo</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: cols }).map((__, j) => (
                      <td key={j}><span className="skeleton skel-20" /></td>
                    ))}
                  </tr>
                ))
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={cols} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>
                    No hay resultados.
                  </td>
                </tr>
              ) : (
                items.map((a: any) => (
                  <tr key={a.sku ?? a.Sku}>
                    <td className="mono">{a.sku ?? a.Sku}</td>
                    <td>{a.descripcion ?? a.Descripcion ?? ''}</td>
                    <td>{a.familiaId ?? a.FamiliaId ?? ''}</td>
                    <td>{a.familiaNombre ?? a.FamiliaNombre ?? ''}</td>
                    <td>{a.generoId ?? a.GeneroId ?? ''}</td>
                    <td>{a.generoDescripcion ?? a.GeneroDescripcion ?? ''}</td>
                    <td>{a.seccionId ?? a.SeccionId ?? ''}</td>
                    <td>{a.seccionNombre ?? a.SeccionNombre ?? ''}</td>
                    <td>{a.marcaId ?? a.MarcaId ?? ''}</td>
                    <td>{a.marcaNombre ?? a.MarcaNombre ?? ''}</td>
                    <td>{a.temporadaId ?? a.TemporadaId ?? ''}</td>
                    <td>{a.temporadaNombre ?? a.TemporadaNombre ?? ''}</td>
                    <td>{a.fecAlta ?? a.FecAlta ?? ''}</td>
                    <td>{a.fecModif ?? a.FecModif ?? ''}</td>
                    <td>{a.comentario ?? a.Comentario ?? ''}</td>
                    <td>{a.factDescMin ?? a.FactDescMin ?? ''}</td>
                    <td>{a.factDescMax ?? a.FactDescMax ?? ''}</td>
                    <td>{a.descValida ?? a.DescValida ?? ''}</td>
                    <td>{a.stockMinimo ?? a.StockMinimo ?? 0}</td>
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
