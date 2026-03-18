import { useEffect, useMemo, useState } from 'react';
import api from '../../../api/client';
import BackToDashboardButton from '../../users/components/BackToDashboardButton';
import ScrollToTopButton from '../../users/components/ScrollToTopButton';
import Modal from '../../users/components/shared/Modal';

export default function ArticulosPage() {
  const [skuInput, setSkuInput] = useState('');
  const [sku, setSku] = useState('');
  const [familiaInput, setFamiliaInput] = useState('');
  const [familia, setFamilia] = useState('');
  const [generoInput, setGeneroInput] = useState('');
  const [genero, setGenero] = useState('');
  const [items, setItems] = useState<any[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [familias, setFamilias] = useState<string[]>([]);
  const [generos, setGeneros] = useState<string[]>([]);
  const [selectedArticulo, setSelectedArticulo] = useState<any | null>(null);

  useEffect(() => {
    api.get('/api/Articulos/distinct-familias').then(r => setFamilias(r.data ?? [])).catch(() => {});
    api.get('/api/Articulos/distinct-generos').then(r => setGeneros(r.data ?? [])).catch(() => {});
  }, []);

  const fetchPage = async (pageNum: number, skuFilter: string, familiaFilter: string, generoFilter: string, ps = pageSize) => {
    setIsLoading(true);
    try {
      const params: any = { page: pageNum, pageSize: ps };
      if (skuFilter && skuFilter.trim() !== '') params.sku = skuFilter.trim();
      if (familiaFilter && familiaFilter.trim() !== '') params.familiaNombre = familiaFilter.trim();
      if (generoFilter && generoFilter.trim() !== '') params.generoDescripcion = generoFilter.trim();
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

  useEffect(() => { fetchPage(page, sku, familia, genero, pageSize); }, [page, sku, familia, genero, pageSize]);

  const handleSearch = () => {
    setSku(skuInput);
    setFamilia(familiaInput);
    setGenero(generoInput);
    setPage(1);
  };

  const handleReset = () => {
    setSkuInput('');
    setSku('');
    setFamiliaInput('');
    setFamilia('');
    setGeneroInput('');
    setGenero('');
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
          <h1 className="section-title">Artículos</h1>
          <p className="section-subtitle">Listado de artículos cargados en la base de datos.</p>
        </header>

        <section className="card filters-card articulos-filtros">
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
              <label className="label">Familia</label>
              <input
                className="input"
                list="articulos-familia-list"
                placeholder="Todos"
                value={familiaInput}
                onChange={e => setFamiliaInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
              <datalist id="articulos-familia-list">
                {familias.map(f => <option key={f} value={f} />)}
              </datalist>
            </div>

            <div className="form-row">
              <label className="label">Género</label>
              <input
                className="input"
                list="articulos-genero-list"
                placeholder="Todos"
                value={generoInput}
                onChange={e => setGeneroInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
              <datalist id="articulos-genero-list">
                {generos.map(g => <option key={g} value={g} />)}
              </datalist>
            </div>
          </div>
          <div className="filters-actions">
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
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i}>
                      <td><span className="skeleton skel-20" /></td>
                      <td><span className="skeleton skel-20" /></td>
                    </tr>
                  ))
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={2} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>
                      No hay resultados.
                    </td>
                  </tr>
                ) : (
                  items.map((a: any) => (
                    <tr key={a.sku ?? a.Sku} style={{ cursor: 'pointer' }} onClick={() => setSelectedArticulo(a)}>
                      <td className="mono" style={{ color: 'var(--emerald-700)', fontWeight: 700 }}>{a.sku ?? a.Sku}</td>
                      <td>{a.descripcion ?? a.Descripcion ?? ''}</td>
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

      {selectedArticulo && (
        <Modal title={`Detalle — ${selectedArticulo.sku ?? selectedArticulo.Sku}`} onClose={() => setSelectedArticulo(null)} maxWidth="52rem">
          <div style={{ maxWidth: '100%' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem 1.5rem' }}>
              {[
                ['Código de Barras',selectedArticulo.barcode          ?? selectedArticulo.Barcode          ?? '—'],
                ['Descripción',    selectedArticulo.descripcion      ?? selectedArticulo.Descripcion      ?? '—'],
                ['Familia ID',     selectedArticulo.familiaId        ?? selectedArticulo.FamiliaId        ?? '—'],
                ['Familia',        selectedArticulo.familiaNombre     ?? selectedArticulo.FamiliaNombre    ?? '—'],
                ['Género ID',      selectedArticulo.generoId         ?? selectedArticulo.GeneroId         ?? '—'],
                ['Género',         selectedArticulo.generoDescripcion ?? selectedArticulo.GeneroDescripcion ?? '—'],
                ['Sección ID',     selectedArticulo.seccionId        ?? selectedArticulo.SeccionId        ?? '—'],
                ['Sección',        selectedArticulo.seccionNombre     ?? selectedArticulo.SeccionNombre    ?? '—'],
                ['Marca ID',       selectedArticulo.marcaId          ?? selectedArticulo.MarcaId          ?? '—'],
                ['Marca',          selectedArticulo.marcaNombre       ?? selectedArticulo.MarcaNombre      ?? '—'],
                ['Temporada ID',   selectedArticulo.temporadaId      ?? selectedArticulo.TemporadaId      ?? '—'],
                ['Temporada',      (selectedArticulo.temporadaNombre ?? selectedArticulo.TemporadaNombre ?? 'Sin definir').replace(/^\{(.*)\}$/, '$1')],
                ['Stock Mínimo',   selectedArticulo.stockMinimo      ?? selectedArticulo.StockMinimo      ?? 0],
                ['Comentario',     selectedArticulo.comentario       ?? selectedArticulo.Comentario       ?? 'Sin definir'],
                ['Fact Desc Min',  selectedArticulo.factDescMin      ?? selectedArticulo.FactDescMin      ?? '—'],
                ['Fact Desc Max',  selectedArticulo.factDescMax      ?? selectedArticulo.FactDescMax      ?? '—'],
                ['Desc Válida',    selectedArticulo.descValida       ?? selectedArticulo.DescValida       ?? '—'],
                ['Frecuencia Mens.',selectedArticulo.frecuenciaMensual ?? selectedArticulo.FrecuenciaMensual ?? '—'],
              ].map(([label, value]) => (
                <div key={label as string}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--muted)', marginBottom: '0.2rem' }}>
                    {label}
                  </div>
                  <div style={{ fontSize: '0.95rem', color: 'var(--emerald-950)', wordBreak: 'break-word' }}>
                    {String(value)}
                  </div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: '1.5rem', display: 'flex', justifyContent: 'flex-end' }}>
              <button className="button button-ghost" onClick={() => setSelectedArticulo(null)}>Cerrar</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
