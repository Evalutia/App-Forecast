import React from 'react';
import type { JobsQuery } from '../../jobs/types/jobs';
import TablaJobs from '../../jobs/components/TablaJobs';
import BackToDashboardButton from '../../users/components/BackToDashboardButton';

const ESTADOS = ['pendiente', 'ejecutando', 'exitoso', 'fallido', 'cancelado'];

export default function JobsPage() {
  const [query, setQuery] = React.useState<JobsQuery>({
    page: 1,
    pageSize: 50,
    tipo: '',
    estado: '',
    desde: '',
    hasta: '',
  });

  const onChange =
    <K extends keyof JobsQuery>(k: K) =>
    (v: JobsQuery[K]) =>
      setQuery((q) => ({ ...q, [k]: v, page: 1 }));

  return (
    <div className="mx-auto max-w-6xl p-4 md:p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Jobs</h1>
        <BackToDashboardButton />
      </div>

      {/* Filtros */}
      <div className="mb-4 rounded-xl ring-1 ring-slate-200 bg-white p-4">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <div className="md:col-span-2">
            <label className="block text-xs font-semibold text-slate-600 mb-1">
              Tipo de job
            </label>
            <input
              type="text"
              className="w-full rounded-lg ring-1 ring-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder="p.ej. forecast, etl, etc."
              value={query.tipo ?? ''}
              onChange={(e) => onChange('tipo')(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">
              Estado
            </label>
            <select
              className="w-full rounded-lg ring-1 ring-slate-300 px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
              value={query.estado ?? ''}
              onChange={(e) => onChange('estado')(e.target.value)}
            >
              <option value="">Todos</option>
              {ESTADOS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">
              Desde
            </label>
            <input
              type="date"
              className="w-full rounded-lg ring-1 ring-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              value={query.desde ?? ''}
              onChange={(e) => onChange('desde')(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">
              Hasta
            </label>
            <input
              type="date"
              className="w-full rounded-lg ring-1 ring-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              value={query.hasta ?? ''}
              onChange={(e) => onChange('hasta')(e.target.value)}
            />
          </div>
        </div>

        <div className="mt-3 flex items-center justify-between">
          <div className="text-xs text-slate-500">
            Los filtros se aplican automáticamente.
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-slate-600">Por página</label>
            <select
              className="rounded-lg ring-1 ring-slate-300 px-2 py-1 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
              value={query.pageSize}
              onChange={(e) => onChange('pageSize')(Number(e.target.value))}
            >
              {[20, 50, 100].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Tabla */}
      <TablaJobs query={query} onQueryChange={setQuery} />
    </div>
  );
}
