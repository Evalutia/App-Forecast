import { useEffect, useMemo, useRef, useState } from 'react';
import api from '../../../api/client';
import '../../../styles/articulos.css';

type Art = Record<string, unknown>;

const pick = (a: Art, k: string): unknown =>
  a[k] ?? a[`${k.charAt(0).toUpperCase()}${k.slice(1)}`];

const str = (a: Art, ...keys: string[]): string =>
  String(keys.reduce<unknown>((v, k) => v ?? pick(a, k), undefined) ?? '—');

export default function ArticulosPage() {
  const [skuInput, setSkuInput]         = useState('');
  const [sku, setSku]                   = useState('');
  const [familiaInput, setFamiliaInput] = useState('');
  const [familia, setFamilia]           = useState('');
  const [generoInput, setGeneroInput]   = useState('');
  const [genero, setGenero]             = useState('');
  const [items, setItems]               = useState<Art[]>([]);
  const [page, setPage]                 = useState(1);
  const [pageSize, setPageSize]         = useState(20);
  const [total, setTotal]               = useState(0);
  const [isLoading, setIsLoading]       = useState(false);
  const [familias, setFamilias]         = useState<string[]>([]);
  const [generos, setGeneros]           = useState<string[]>([]);
  const [selected, setSelected]         = useState<Art | null>(null);

  const filterRef = useRef<HTMLElement | null>(null);
  const tableRef  = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const els = [filterRef.current, tableRef.current].filter(Boolean) as HTMLElement[];
    const obs = new IntersectionObserver(
      entries => entries.forEach(e => {
        if (e.isIntersecting) { (e.target as HTMLElement).classList.add('visible'); obs.unobserve(e.target); }
      }),
      { threshold: 0.04 }
    );
    els.forEach(el => obs.observe(el));
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    api.get('/api/Articulos/distinct-familias').then(r => setFamilias(r.data ?? [])).catch(() => {});
  }, []);

  useEffect(() => {
    const params: Record<string, string> = {};
    if (familiaInput.trim()) params.familia = familiaInput.trim();
    api.get('/api/Articulos/distinct-generos', { params })
      .then(r => {
        setGeneros(r.data ?? []);
        if (familiaInput.trim() && generoInput && !(r.data ?? []).includes(generoInput)) setGeneroInput('');
      })
      .catch(() => {});
  }, [familiaInput]);

  const fetchPage = async (pageNum: number, skuF: string, familiaF: string, generoF: string, ps = pageSize) => {
    setIsLoading(true);
    try {
      const params: Record<string, unknown> = { page: pageNum, pageSize: ps };
      if (skuF.trim())     params.sku              = skuF.trim();
      if (familiaF.trim()) params.familiaNombre     = familiaF.trim();
      if (generoF.trim())  params.generoDescripcion = generoF.trim();
      const res  = await api.get('/api/Articulos', { params });
      const data = res.data as Art;
      const out  = (data['items'] ?? data['Items'] ?? data) as unknown;
      const rows = Array.isArray(out) ? (out as Art[]) : [];
      setItems(rows);
      setTotal(Number(data['total'] ?? data['Total'] ?? rows.length));
    } catch {
      setItems([]);
      setTotal(0);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { fetchPage(page, sku, familia, genero, pageSize); }, [page, sku, familia, genero, pageSize]);

  const handleSearch = () => { setSku(skuInput); setFamilia(familiaInput); setGenero(generoInput); setPage(1); };
  const handleReset  = () => { setSkuInput(''); setSku(''); setFamiliaInput(''); setFamilia(''); setGeneroInput(''); setGenero(''); setPage(1); };

  const totalPages = useMemo(() => Math.max(1, Math.ceil((total || 0) / pageSize)), [total, pageSize]);

  return (
    <div className="art-page">

      {/* ── Header ── */}
      <header className="art-header">
        <a href="/home" className="art-brand">Evalutia</a>
        <a href="/home" className="art-back-btn">← Dashboard</a>
      </header>

      {/* ── Hero ── */}
      <section className="art-hero">
        <div className="art-hero-grid" />
        <div className="art-hero-glow" />
        <div className="art-hero-content">
          <h1 className="art-title">Artículos</h1>
          <p className="art-subtitle">Catálogo completo de productos del sistema.</p>
          {total > 0 && (
            <div className="art-stat-pill">{total.toLocaleString('es-UY')} artículos</div>
          )}
        </div>
      </section>

      {/* ── Content ── */}
      <div className="art-container">

        {/* Filters */}
        <section className="art-filter-card art-reveal" ref={filterRef}>
          <div className="art-filters-grid">
            <div className="art-form-row">
              <label className="art-label">SKU</label>
              <input
                className="art-input"
                placeholder="ej. I01497"
                value={skuInput}
                onChange={e => setSkuInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <div className="art-form-row">
              <label className="art-label">Familia</label>
              <input
                className="art-input"
                list="art-familia-list"
                placeholder="Todas"
                value={familiaInput}
                onChange={e => setFamiliaInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
              <datalist id="art-familia-list">
                {familias.map(f => <option key={f} value={f} />)}
              </datalist>
            </div>
            <div className="art-form-row">
              <label className="art-label">Género</label>
              <input
                className="art-input"
                list="art-genero-list"
                placeholder="Todos"
                value={generoInput}
                onChange={e => setGeneroInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
              <datalist id="art-genero-list">
                {generos.map(g => <option key={g} value={g} />)}
              </datalist>
            </div>
          </div>
          <div className="art-filter-actions">
            <button type="button" className="art-btn" onClick={handleSearch}>Buscar</button>
            <button type="button" className="art-btn-ghost" onClick={handleReset}>Limpiar</button>
          </div>
        </section>

        {/* Table */}
        <section className="art-table-card art-reveal" ref={tableRef}>
          <div className="art-table-wrap">
            <table className="art-table">
              <thead>
                <tr>
                  <th className="art-th-sku">SKU</th>
                  <th>Descripción</th>
                  <th>Familia</th>
                  <th>Género</th>
                  <th>Marca</th>
                  <th>Stock Mín.</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  Array.from({ length: 10 }).map((_, i) => (
                    <tr key={i}>
                      <td><span className="art-skeleton art-skeleton-sm" /></td>
                      <td><span className="art-skeleton art-skeleton-lg" /></td>
                      <td><span className="art-skeleton art-skeleton-md" /></td>
                      <td><span className="art-skeleton art-skeleton-md" /></td>
                      <td><span className="art-skeleton art-skeleton-md" /></td>
                      <td><span className="art-skeleton art-skeleton-sm" /></td>
                    </tr>
                  ))
                ) : items.length === 0 ? (
                  <tr><td colSpan={6} className="art-empty">No hay resultados.</td></tr>
                ) : (
                  items.map(a => {
                    const sku = str(a, 'sku');
                    const marca = String(pick(a, 'marcaNombre') ?? '');
                    const stock = pick(a, 'stockMinimo');
                    return (
                      <tr key={sku} onClick={() => setSelected(a)}>
                        <td className="art-td-sku">{sku}</td>
                        <td className="art-td-desc">{str(a, 'descripcion')}</td>
                        <td>{str(a, 'familiaNombre')}</td>
                        <td>{str(a, 'generoDescripcion')}</td>
                        <td className="art-td-badge">
                          {marca ? <span className="art-badge">{marca}</span> : '—'}
                        </td>
                        <td>
                          {stock != null
                            ? <span className="art-badge art-badge-stock">{String(stock)}</span>
                            : '—'}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="art-pager">
            <span className="art-pager-info">
              Página <strong>{page}</strong> de <strong>{totalPages}</strong> — Total: <strong>{total}</strong>
            </span>
            <div className="art-pager-right">
              <select
                className="art-page-size-select"
                value={pageSize}
                onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}
              >
                {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n} filas</option>)}
              </select>
              <button className="art-pager-btn" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Anterior</button>
              <button className="art-pager-btn" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Siguiente</button>
            </div>
          </div>
        </section>

      </div>

      {/* ── Detail modal ── */}
      {selected && (
        <div
          className="art-modal-overlay"
          onClick={e => { if (e.target === e.currentTarget) setSelected(null); }}
        >
          <div className="art-modal">
            <div className="art-modal-header">
              <h2 className="art-modal-title">{str(selected, 'sku')}</h2>
              <button className="art-modal-close" onClick={() => setSelected(null)}>✕</button>
            </div>

            <div className="art-modal-grid">
              {([
                ['Código de Barras', str(selected, 'barcode')],
                ['Descripción',      str(selected, 'descripcion')],
                ['Familia',          str(selected, 'familiaNombre')],
                ['Género',           str(selected, 'generoDescripcion')],
                ['Sección',          str(selected, 'seccionNombre')],
                ['Marca',            str(selected, 'marcaNombre')],
                ['Temporada',        String(pick(selected, 'temporadaNombre') ?? 'Sin definir')
                                       .replace(/^\{(.*)\}$/, '$1')
                                       .replace(/^Sin Definir$/i, 'Sin definir')],
                ['Stock Mínimo',     str(selected, 'stockMinimo')],
                ['Comentario',       str(selected, 'comentario')],
                ['Fact Desc Min',    str(selected, 'factDescMin')],
                ['Fact Desc Max',    str(selected, 'factDescMax')],
                ['Desc Válida',      str(selected, 'descValida')],
                ['Frecuencia Mens.', str(selected, 'frecuenciaMensual')],
              ] as [string, string][]).map(([label, value]) => (
                <div key={label}>
                  <div className="art-modal-field-label">{label}</div>
                  <div className="art-modal-field-value">{value}</div>
                </div>
              ))}
            </div>

            <div className="art-modal-footer">
              <button className="art-btn-ghost" onClick={() => setSelected(null)}>Cerrar</button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
