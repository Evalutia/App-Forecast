import './ChartSetup';
import { Doughnut } from 'react-chartjs-2';
import { useStockoutDistribution } from '../../hooks/useResultados';

export default function StockoutDistributionChart() {
  const { data, isLoading } = useStockoutDistribution();

  if (isLoading) return <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>Cargando...</div>;
  if (!data) return null;

  const total = data.bueno + data.moderado + data.critico + data.sinDatos;
  if (total === 0) {
    return (
      <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--muted)' }}>
        No hay artículos con stock mínimo configurado.
      </div>
    );
  }

  const chartData = {
    labels: [
      `Bueno (≤15%) — ${data.bueno}`,
      `Moderado (15–30%) — ${data.moderado}`,
      `Crítico (>30%) — ${data.critico}`,
      `Sin datos suficientes — ${data.sinDatos}`,
    ],
    datasets: [{
      data: [data.bueno, data.moderado, data.critico, data.sinDatos],
      backgroundColor: ['#16a34a', '#d97706', '#dc2626', '#9ca3af'],
      borderWidth: 0,
    }],
  };

  return (
    <div className="card" style={{ padding: '1.25rem' }}>
      <h3 style={{ fontSize: '0.85rem', fontWeight: 800, marginBottom: '0.5rem', color: 'var(--emerald-950)' }}>
        Distribución de stockout por SKU
      </h3>
      <p style={{ fontSize: '0.72rem', color: 'var(--muted)', marginBottom: '0.75rem' }}>
        Clasificación de productos según su tasa de quiebre de stock en los últimos 365 días.
      </p>
      <div style={{ maxWidth: '320px', margin: '0 auto' }}>
        <Doughnut data={chartData} options={{
          responsive: true,
          plugins: {
            legend: {
              position: 'bottom',
              labels: { padding: 12, font: { size: 11 } },
            },
          },
        }} />
      </div>
    </div>
  );
}
