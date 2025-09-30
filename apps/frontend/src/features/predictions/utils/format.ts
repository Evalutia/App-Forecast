import type { Prediccion } from '../types/predicciones';

export function getSkuBase(sku: string): string {
  const m = sku.match(/^(.*?)-\d{4}-\d{2}-\d{2}$/);
  return m ? m[1] : sku;
}

export function fmtYearMonth(d: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return d.slice(0, 7);
  return d.slice(0, 7); // fallback defensivo
}

export function fmtDateHour(iso: string): string {
  const parts = iso.replace('T', ' ').split(' ');
  if (parts.length < 2) return iso;
  const [date, time] = parts;
  const hour = time.split(':')[0] ?? '00';
  return `${date} ${hour}`;
}

export function horizonLabel(h: number | null | undefined): string {
  if (typeof h === 'number' && h > 0) return `Mes ${h}`;
  return 'h=?';
}

export function ascendingYYYYMM(a: string, b: string) {
  return a.slice(0, 7).localeCompare(b.slice(0, 7));
}

export function groupAvgByModelo(preds: Prediccion[]) {
  const acc: Record<string, { r2Sum: number; r2Cnt: number; rmseSum: number; rmseCnt: number }> = {};
  preds.forEach(p => {
    const key = p.modelo || '—';
    if (!acc[key]) acc[key] = { r2Sum: 0, r2Cnt: 0, rmseSum: 0, rmseCnt: 0 };
    if (typeof p.r2 === 'number') { acc[key].r2Sum += p.r2; acc[key].r2Cnt += 1; }
    if (typeof p.rmse === 'number') { acc[key].rmseSum += p.rmse; acc[key].rmseCnt += 1; }
  });
  return Object.entries(acc).map(([modelo, v]) => ({
    modelo,
    r2Avg: v.r2Cnt ? v.r2Sum / v.r2Cnt : null,
    rmseAvg: v.rmseCnt ? v.rmseSum / v.rmseCnt : null,
  }));
}

export function toYearMonth(d: string): string {
  return d.slice(0, 7); // "YYYY-MM"
}

export function pickMonthlyProjection(
  items: Prediccion[],
  preferModelo: string | null = 'COMBINADA'
) {
  const byYm = new Map<string, Prediccion>();

  const isBetter = (curr: Prediccion | undefined, cand: Prediccion) => {
    if (!curr) return true;
    if (preferModelo && cand.modelo === preferModelo && curr.modelo !== preferModelo) return true;
    if (preferModelo && curr.modelo === preferModelo && cand.modelo !== preferModelo) return false;
    return (cand.tsGeneracion ?? '') > (curr.tsGeneracion ?? '');
  };

  for (const p of items) {
    const ym = toYearMonth(p.fechaPredicha);
    const curr = byYm.get(ym);
    if (isBetter(curr, p)) byYm.set(ym, p);
  }

  const labels = Array.from(byYm.keys()).sort();
  const values = labels.map((ym) => byYm.get(ym)!.cantidadPredicha);
  return { labels, values };
}
