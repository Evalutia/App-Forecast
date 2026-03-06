import { useEffect, useMemo, useState } from 'react';
import api from '../../../api/client';
import BackToDashboardButton from '../../users/components/BackToDashboardButton';
import ScrollToTopButton from '../../users/components/ScrollToTopButton';

export default function ArticulosPage() {
  const [skuInput, setSkuInput] = useState('');
  const [sku, setSku] = useState('');
  const [items, setItems] = useState<any[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  const fetchPage = async (pageNum: number, skuFilter: string, ps = pageSize) => {
    setIsLoading(true);
    try {
      const params: any = { page: pageNum, pageSize: ps };
      if (skuFilter && skuFilter.trim() !== '') params.sku = skuFilter.trim();
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

  useEffect(() => { fetchPage(page, sku, pageSize); }, [page, sku, pageSize]);

  const handleSearch = () => {
    setSku(skuInput);
    setPage(1);
  };

  const handleReset = () => {
    setSkuInput('');
    setSku('');
    setPage(1);
  };

  const totalPages = useMemo(() => Math.max(1, Math.ceil((total || 0) / pageSize)), [total, pageSize]);

  const cols = 19;

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
          <h1 className="section-title">Artículos</h1>
          <p className="section-subtitle">Listado de artículos cargados en la base de datos.</p>
        </header>

        <section className="card filters-card">
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <div className="form-row" style={{ width: '300px' }}>
              <label className="label">SKU</label>
              <input
                className="input"
                placeholder="p.ej. I01497"
                value={skuInput}
                onChange={e => setSkuInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
            </div>
          </div>
          <div className="filters-actions" style={{ justifyContent: 'center' }}>
            <button type="button" className="button" onClick={handleSearch}>Buscar</button>
            <button type="button" className="button button-ghost" onClick={handleReset}>Limpiar</button>
          </div>
        </section>

        <section className="card table-card">
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

          <div className="pager">
            <div>Página {page} de {totalPages} — Total: <strong>{total}</strong></div>
            <div className="pager-buttons">
              <button className="pager-btn" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Anterior</button>
              <button className="pager-btn" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Siguiente</button>
            </div>
          </div>
          <div style={{ marginTop: '.5rem' }} className="muted">
            Filas por página:&nbsp;
            <select
              value={pageSize}
              onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
            >
              {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
        </section>
      </div>
      <ScrollToTopButton />
    </div>
  );
}
