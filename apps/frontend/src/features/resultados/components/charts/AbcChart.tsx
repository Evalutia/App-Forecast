import './ChartSetup';
import { Doughnut } from 'react-chartjs-2';
import { useAbcClassification } from '../../hooks/useResultados';

export default function AbcChart() {
  const { data, isLoading } = useAbcClassification();

  if (isLoading) return <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>Cargando...</div>;
  if (!data || data.items.length === 0) {
    return (
      <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--muted)' }}>
        Sin datos de ventas para clasificar.
      </div>
    );
  }

  const total = data.cantidadA + data.cantidadB + data.cantidadC;
  const pctA = total > 0 ? Math.round(data.cantidadA / total * 100) : 0;
  const pctB = total > 0 ? Math.round(data.cantidadB / total * 100) : 0;
  const pctC = total > 0 ? Math.round(data.cantidadC / total * 100) : 0;

  const chartData = {
    labels: [
      `A — ${data.cantidadA} SKUs (${pctA}%)`,
      `B — ${data.cantidadB} SKUs (${pctB}%)`,
      `C — ${data.cantidadC} SKUs (${pctC}%)`,
    ],
    datasets: [{
      data: [data.cantidadA, data.cantidadB, data.cantidadC],
      backgroundColor: ['#059669', '#0ea5e9', '#94a3b8'],
      borderWidth: 0,
    }],
  };

  return (
    <div className="card" style={{ padding: '1.25rem' }}>
      <h3 style={{ fontSize: '0.85rem', fontWeight: 800, marginBottom: '0.5rem', color: 'var(--emerald-950)' }}>
        Clasificación ABC de productos
      </h3>
      <p style={{ fontSize: '0.72rem', color: 'var(--muted)', marginBottom: '0.75rem' }}>
        Análisis de Pareto: <strong>A</strong> = top 80% de ventas (los más importantes), 
        <strong> B</strong> = siguiente 15%, <strong> C</strong> = último 5%. 
        Enfocá la reposición en los productos A.
      </p>
      <div style={{ display: 'flex', alignItems: 'center', gap: '2rem', flexWrap: 'wrap' }}>
        <div style={{ maxWidth: '280px', flex: '0 0 280px' }}>
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
        <div style={{ flex: 1, minWidth: '200px' }}>
          {[
            { cls: 'A', count: data.cantidadA, color: '#059669', desc: 'Alta rotación — prioridad máxima de reposición' },
            { cls: 'B', count: data.cantidadB, color: '#0ea5e9', desc: 'Rotación media — monitorear regularmente' },
            { cls: 'C', count: data.cantidadC, color: '#94a3b8', desc: 'Baja rotación — revisar si conviene mantener stock' },
          ].map(r => (
            <div key={r.cls} style={{ marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{
                  display: 'inline-block',
                  width: '28px',
                  height: '28px',
                  borderRadius: '6px',
                  background: r.color,
                  color: '#fff',
                  fontWeight: 900,
                  fontSize: '0.8rem',
                  textAlign: 'center',
                  lineHeight: '28px',
                }}>{r.cls}</span>
                <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>
                  {r.count} SKUs
                </span>
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--muted)', marginLeft: '2.25rem' }}>
                {r.desc}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
