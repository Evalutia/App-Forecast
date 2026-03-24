import './ChartSetup';
import { useState } from 'react';
import { Doughnut } from 'react-chartjs-2';
import { useStockoutDistribution } from '../../hooks/useResultados';
import type { StockoutItem } from '../../types/resultados';

const CATEGORIES = [
  { key: 'Bueno', label: 'Bueno (≤15%)', color: '#16a34a' },
  { key: 'Moderado', label: 'Moderado (15–30%)', color: '#d97706' },
  { key: 'Critico', label: 'Crítico (>30%)', color: '#dc2626' },
  { key: 'SinDatos', label: 'Sin datos suficientes', color: '#9ca3af' },
] as const;

export default function StockoutDistributionChart() {
  const { data, isLoading } = useStockoutDistribution();
  const [selected, setSelected] = useState<string | null>(null);

  if (isLoading) return <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>Cargando...</div>;
  if (!data) return null;

  const counts: Record<string, number> = {
    Bueno: data.bueno,
    Moderado: data.moderado,
    Critico: data.critico,
    SinDatos: data.sinDatos,
  };

  const total = data.bueno + data.moderado + data.critico + data.sinDatos;
  if (total === 0) {
    return (
      <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--muted)' }}>
        No hay artículos con stock mínimo configurado.
      </div>
    );
  }

  const chartData = {
    labels: CATEGORIES.map(c => `${c.label} — ${counts[c.key]}`),
    datasets: [{
      data: CATEGORIES.map(c => counts[c.key]),
      backgroundColor: CATEGORIES.map(c => c.color),
      borderWidth: 0,
    }],
  };

  const filteredItems = selected && data.items
    ? data.items.filter(i => i.categoria === selected)
    : [];

  return (
    <div className="card" style={{ padding: '1.25rem' }}>
      <h3 style={{ fontSize: '0.85rem', fontWeight: 800, marginBottom: '0.5rem', color: 'var(--emerald-950)' }}>
        Distribución de stockout por SKU
      </h3>
      <p style={{ fontSize: '0.72rem', color: 'var(--muted)', marginBottom: '0.75rem' }}>
        Clasificación de productos según su tasa de quiebre de stock en los últimos 365 días. Hacé clic en una categoría para ver los SKUs.
      </p>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1.5rem', flexWrap: 'wrap' }}>
        <div style={{ maxWidth: '260px', flex: '0 0 260px' }}>
          <Doughnut data={chartData} options={{
            responsive: true,
            plugins: {
              legend: { display: false },
            },
          }} />
        </div>
        <div style={{ flex: 1, minWidth: '180px' }}>
          {CATEGORIES.map(c => (
            <div
              key={c.key}
              style={{
                marginBottom: '0.6rem',
                cursor: 'pointer',
                padding: '0.35rem 0.5rem',
                borderRadius: '0.5rem',
                background: selected === c.key ? `${c.color}12` : 'transparent',
                border: selected === c.key ? `1.5px solid ${c.color}40` : '1.5px solid transparent',
                transition: 'all .15s ease',
              }}
              onClick={() => setSelected(selected === c.key ? null : c.key)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{
                  display: 'inline-block',
                  width: '12px',
                  height: '12px',
                  borderRadius: '3px',
                  background: c.color,
                  flexShrink: 0,
                }} />
                <span style={{ fontWeight: 700, fontSize: '0.82rem' }}>
                  {c.label} — {counts[c.key]}
                </span>
                <span style={{ fontSize: '0.68rem', color: 'var(--muted)', marginLeft: 'auto' }}>
                  {selected === c.key ? '▲' : '▼'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {selected && filteredItems.length > 0 && (
        <StockoutItemsTable items={filteredItems} categoria={selected} />
      )}
    </div>
  );
}

function StockoutItemsTable({ items, categoria }: { items: StockoutItem[]; categoria: string }) {
  const colorMap: Record<string, string> = { Bueno: '#16a34a', Moderado: '#d97706', Critico: '#dc2626', SinDatos: '#9ca3af' };
  const color = colorMap[categoria] ?? '#6b7280';

  return (
    <div style={{ marginTop: '1rem', maxHeight: '300px', overflowY: 'auto', border: `1px solid ${color}30`, borderRadius: '0.75rem' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
        <thead>
          <tr style={{ background: '#f0fdf4', position: 'sticky', top: 0, zIndex: 1 }}>
            <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left', fontWeight: 800, color }}>SKU</th>
            <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left', fontWeight: 800, color }}>Descripción</th>
            <th style={{ padding: '0.5rem 0.75rem', textAlign: 'right', fontWeight: 800, color }}>Stockout Rate</th>
          </tr>
        </thead>
        <tbody>
          {items.map(i => (
            <tr key={i.sku} style={{ borderTop: '1px solid #e5e7eb40' }}>
              <td style={{ padding: '0.4rem 0.75rem', fontWeight: 600 }}>{i.sku}</td>
              <td style={{ padding: '0.4rem 0.75rem', color: 'var(--muted)' }}>{i.descripcion ?? '—'}</td>
              <td style={{ padding: '0.4rem 0.75rem', textAlign: 'right' }}>
                {i.stockoutRate >= 0 ? `${i.stockoutRate}%` : 'N/A'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
