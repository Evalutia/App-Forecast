import { useResumenGlobal } from '../hooks/useResultados';

function formatNum(n: number | null | undefined): string {
  if (n == null) return '—';
  return n.toLocaleString('es-AR');
}

export default function ResumenCards() {
  const { data, isLoading } = useResumenGlobal();

  const cards = [
    {
      label: 'SKUs analizados',
      value: isLoading ? '...' : formatNum(data?.totalSkus),
      color: 'var(--emerald-700)',
    },
    {
      label: 'SKUs con quiebre de stock',
      value: isLoading ? '...' : formatNum(data?.skusConStockout),
      color: (data?.skusConStockout ?? 0) > 0 ? '#dc2626' : 'var(--emerald-700)',
    },
    {
      label: 'Tasa de stockout promedio',
      value: isLoading ? '...' : `${data?.stockoutRatePromedio ?? 0}%`,
      color: (data?.stockoutRatePromedio ?? 0) > 30 ? '#dc2626' : (data?.stockoutRatePromedio ?? 0) > 15 ? '#d97706' : 'var(--emerald-700)',
    },
    {
      label: 'Ventas perdidas estimadas (365d)',
      value: isLoading ? '...' : formatNum(data?.ventasPerdidasTotales),
      color: (data?.ventasPerdidasTotales ?? 0) > 0 ? '#dc2626' : 'var(--emerald-700)',
    },
    {
      label: 'Última predicción',
      value: isLoading ? '...' : (data?.ultimaPrediccion ?? '—'),
      color: 'var(--emerald-700)',
    },
  ];

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
      gap: '1rem',
      marginBottom: '1.5rem',
    }}>
      {cards.map((c) => (
        <div key={c.label} className="card" style={{ padding: '1.1rem 1.25rem' }}>
          <div style={{
            fontSize: '0.72rem',
            fontWeight: 800,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: 'var(--muted)',
            marginBottom: '0.35rem',
          }}>
            {c.label}
          </div>
          <div style={{
            fontSize: '1.5rem',
            fontWeight: 900,
            color: c.color,
            fontFamily: "'Montserrat', sans-serif",
          }}>
            {c.value}
          </div>
        </div>
      ))}
    </div>
  );
}
