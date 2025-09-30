import './ChartSetup';
import { Line } from 'react-chartjs-2';
import type { Prediccion } from '../../types/predicciones';
import { getSkuBase, pickMonthlyProjection } from '../../utils/format';

type Props = { data: Prediccion[]; sku: string };

export default function ProjectedSalesChart({ data, sku }: Props) {
  const skuBase = getSkuBase(sku);

  const serieSku = data.filter((p) => getSkuBase(p.sku) === skuBase);

  // ⬇️ Nos quedamos con 1 punto por mes (preferimos COMBINADA, o el más reciente)
  const { labels, values } = pickMonthlyProjection(serieSku, 'COMBINADA');

  const ds = {
    labels,
    datasets: [{ label: `Proyección ${skuBase}`, data: values }],
  };

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <h4 className="text-base font-semibold text-white">Ventas proyectadas</h4>
      <p className="mb-3 text-xs text-emerald-100/70">
        Serie mensual predicha (un valor por mes). Si hay varias corridas/modelos, se prioriza COMBINADA y, si no, la más reciente.
      </p>
      <Line
        data={ds}
        options={{
          responsive: true,
          plugins: { legend: { display: true } },
          scales: {
            x: {
              ticks: { autoSkip: true, maxTicksLimit: 12 }, 
            },
            y: { beginAtZero: true },
          },
          elements: { point: { radius: 2 } },
        }}
      />
    </div>
  );
}
