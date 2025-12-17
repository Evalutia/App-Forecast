import './ChartSetup';
import { Line } from 'react-chartjs-2';
import type { Prediccion } from '../../types/predicciones';
import { getSkuBase, pickQuarterlyProjection } from '../../utils/format';
import { useVentasAgregadas } from '../../../sales/hooks/useVentas';

type Props = { data: Prediccion[]; sku: string };

export default function ProjectedSalesChart({ data, sku }: Props) {
  const skuBase = getSkuBase(sku);

  const serieSku = data.filter((p) => getSkuBase(p.sku) === skuBase);

  // Predicciones: agrupar por trimestre
  const { labels: predQLabels, values: predQValues } = pickQuarterlyProjection(serieSku, 'COMBINADA');

  // Ventas históricas agregadas trimestralmente (desde endpoint de ventas)
  // pedimos agregación trimestral al backend que ya agrupa por trimestre
  // limitar histórico a los últimos 3 años pero asegurando incluir 2022-Q4
  const now = new Date();
  const cutoff = new Date(now);
  cutoff.setFullYear(now.getFullYear() - 3);
  // Asegurar que el cutoff no sea posterior a 2022-Q4
  const cutoff2022Q4 = new Date('2022-10-01'); // Inicio de Q4 2022
  const finalCutoff = cutoff > cutoff2022Q4 ? cutoff2022Q4 : cutoff;
  const fmt = (d: Date) => d.toISOString().slice(0, 10); // YYYY-MM-DD

  const { data: ventasAg } = useVentasAgregadas(
    { sku: skuBase, agregado: 'trimestral', pageSize: 200, fechaDesde: fmt(finalCutoff) },
    { enabled: true }
  );

  const ventasRows = (ventasAg?.items ?? []).map((r: any) => ({
    // r.periodo viene como "YYYY-QX" para agregado trimestral
    label: r.periodo,
    value: r.totalCantidad,
  }));

  // Unión de labels (histórico + predicciones)
  const labelSet = new Set<string>();
  ventasRows.forEach((r) => labelSet.add(r.label));
  predQLabels.forEach((l) => labelSet.add(l));
  const allLabels = Array.from(labelSet);

  // ordenar por año y trimestre (ej: 2025-Q1)
  allLabels.sort((a, b) => {
    const ma = a.match(/(\d{4})-Q(\d)/);
    const mb = b.match(/(\d{4})-Q(\d)/);
    if (ma && mb) {
      const ya = Number(ma[1]);
      const yb = Number(mb[1]);
      if (ya !== yb) return ya - yb;
      const qa = Number(ma[2]);
      const qb = Number(mb[2]);
      return qa - qb;
    }
    return a.localeCompare(b);
  });

  // sumamos por trimestre (ventasRows ya viene agrupado por trimestre desde backend)
  const ventasMap = new Map<string, number>();
  for (const r of ventasRows) {
    const prev = ventasMap.get(r.label) ?? 0;
    ventasMap.set(r.label, prev + r.value);
  }
  const predMap = new Map(predQLabels.map((l, i) => [l, predQValues[i]]));

  const histData = allLabels.map((lab) => ventasMap.has(lab) ? ventasMap.get(lab) ?? null : null);
  const predData = allLabels.map((lab) => predMap.get(lab) ?? null);

  const noVentasHistoricas = ventasRows.length === 0;

  const datasets: any[] = [];
  if (!noVentasHistoricas) {
    datasets.push({ label: `Ventas históricas (Q) ${skuBase}`, data: histData, borderColor: 'rgba(54,162,235,0.9)', backgroundColor: 'rgba(54,162,235,0.2)' });
  }
  datasets.push({ label: `Predicción (Q) ${skuBase}`, data: predData, borderColor: 'rgba(75,192,192,0.9)', backgroundColor: 'rgba(75,192,192,0.2)', borderDash: [6,4] });

  const ds = { labels: allLabels, datasets };

  return (
    <div className="rounded-xl **border border-white/10** bg-white/5 p-4">
      <h4 className="text-base font-semibold text-white">Ventas proyectadas</h4>
      <p className="mb-3 text-xs text-emerald-100/70">
        Serie trimestral: ventas históricas (acotado a 3 años antes de la predicción) agregadas por trimestre y predicción (un valor por trimestre).
      </p>
      {noVentasHistoricas && (
        <div className="mb-2 text-sm text-amber-100">No se encontraron ventas históricas agregadas para este SKU — mostrando solo predicción.</div>
      )}
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
