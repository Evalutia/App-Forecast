import React from 'react';
import { Link } from 'react-router-dom';
import { useJobs, usePrefetchNextJobsPage } from '../hooks/useJobs';
import type { JobsQuery, JobItem } from '../types/jobs';
import JobEstadoBadge from './JobEstadoBadge';
import JobPrediccionesLink from './JobPrediccionesLink';

type Props = {
  query: JobsQuery;
  onQueryChange: (next: JobsQuery) => void;
  className?: string;
};

function formatDateTime(iso?: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const dd = d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', year: 'numeric' });
  const hh = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  return `${dd} ${hh}`;
}

export default function TablaJobs({ query, onQueryChange, className = '' }: Props) {
  const { data, isLoading, isFetching } = useJobs(query);
  const prefetchNext = usePrefetchNextJobsPage(query);

  const items = data?.items ?? [];
  const page = data?.page ?? query.page ?? 1;
  const pageSize = data?.pageSize ?? query.pageSize ?? 50;
  const total = data?.total ?? 0;

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const canPrev = page > 1;
  const canNext = page < totalPages;

  React.useEffect(() => {
    prefetchNext(items.length).catch(() => {});
  }, [items.length, page, pageSize]);

  const goPage = (p: number) => {
    onQueryChange({ ...query, page: Math.min(Math.max(1, p), totalPages) });
  };

  return (
    <div className={`w-full ${className}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold">Historial de jobs</h3>
        <div className="text-sm text-slate-500">
          {isFetching ? 'Actualizando…' : `Total: ${total}`}
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl ring-1 ring-slate-200">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              <Th>ID</Th>
              <Th>Tipo</Th>
              <Th>Estado</Th>
              <Th>Inicio</Th>
              <Th>Fin</Th>
              <Th className="text-right">Acciones</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {isLoading && items.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-6 text-center text-slate-500">Cargando…</td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-6 text-center text-slate-500">Sin resultados</td>
              </tr>
            ) : (
              items.map((j) => <Row key={j.id} job={j} />)
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <div className="text-sm text-slate-500">
          Página <span className="font-medium">{page}</span> de <span className="font-medium">{totalPages}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="px-3 py-1.5 rounded-lg ring-1 ring-slate-300 text-slate-700 disabled:opacity-40"
            onClick={() => goPage(page - 1)}
            disabled={!canPrev}
          >
            Anterior
          </button>
          <button
            className="px-3 py-1.5 rounded-lg ring-1 ring-slate-300 text-slate-700 disabled:opacity-40"
            onClick={() => goPage(page + 1)}
            disabled={!canNext}
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>
  );
}

function Th({ children, className = '' }: React.PropsWithChildren<{ className?: string }>) {
  return (
    <th className={`px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600 ${className}`}>
      {children}
    </th>
  );
}

function Td({ children, className = '' }: React.PropsWithChildren<{ className?: string }>) {
  return <td className={`px-3 py-2 text-sm text-slate-700 ${className}`}>{children}</td>;
}

function Row({ job }: { job: JobItem }) {
  return (
    <tr>
      <Td className="whitespace-nowrap">#{job.id}</Td>
      <Td className="whitespace-nowrap">{job.tipoJob}</Td>
      <Td><JobEstadoBadge estado={job.estado} /></Td>
      <Td className="whitespace-nowrap">{formatDateTime(job.fechaInicio)}</Td>
      <Td className="whitespace-nowrap">{formatDateTime(job.fechaFin)}</Td>
      <Td className="text-right">
        <div className="inline-flex items-center gap-3">
          <Link
            to={`/jobs/${job.id}`}
            className="text-slate-700 hover:text-slate-900 hover:underline"
          >
            Detalle
          </Link>
          <JobPrediccionesLink jobId={job.id} />
        </div>
      </Td>
    </tr>
  );
}
