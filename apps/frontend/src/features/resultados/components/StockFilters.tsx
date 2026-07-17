type Props = {
  sku: string;
  onSkuChange: (v: string) => void;
  orderBy: string;
  onOrderByChange: (v: string) => void;
  onSearch: () => void;
  onReset: () => void;
};

export default function StockFilters({ sku, onSkuChange, orderBy, onOrderByChange, onSearch, onReset }: Props) {
  return (
    <section className="card filters-card resultados-filtros" style={{ marginBottom: '1rem' }}>
      <div className="filters-grid">
        <div className="form-row">
          <label className="label">SKU</label>
          <input
            className="input"
            placeholder="p.ej. I01497"
            value={sku}
            onChange={e => onSkuChange(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && onSearch()}
          />
        </div>
        <div className="form-row">
          <label className="label">Ordenar por</label>
          <select className="input" value={orderBy} onChange={e => onOrderByChange(e.target.value)}>
            <option value="">SKU (A-Z)</option>
            <option value="stockout">Mayor tasa de stockout</option>
            <option value="ventasperdidas">Más ventas perdidas</option>
            <option value="ventas">Más ventas (365d)</option>
          </select>
        </div>
      </div>
      <div className="filters-actions">
        <button type="button" className="button" onClick={onSearch}>Buscar</button>
        <button type="button" className="button button-ghost" onClick={onReset}>Limpiar</button>
      </div>
    </section>
  );
}
