import React from 'react';
import { useJob } from '../hooks/useJobs';
import JobEstadoBadge from './JobEstadoBadge';

type Props = { jobId: number };

function formatDateTime(iso?: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const dd = d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', year: 'numeric' });
  const hh = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  return `${dd} ${hh}`;
}

export default function JobDetailPanel({ jobId }: Props) {
  const { data: job, isLoading, isFetching } = useJob(jobId);

  if (isLoading && !job) {
    return <div className="p-6 text-slate-500">Cargando…</div>;
  }
  if (!job) {
    return <div className="p-6 text-slate-500">No se encontró el job.</div>;
  }

  return (
    <div className="rounded-xl ring-1 ring-slate-200 bg-white">
      <div className="p-4 flex items-start justify-between border-b border-slate-100">
        <div>
          <h4 className="text-base font-semibold">Job #{job.id}</h4>
          <div className="mt-1 text-sm text-slate-600">
            Tipo: <span className="font-medium">{job.tipoJob}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <JobEstadoBadge estado={job.estado} />
          <span className="text-xs text-slate-500">
            {isFetching ? 'Actualizando…' : null}
          </span>
        </div>
      </div>

      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        <Info label="Inicio" value={formatDateTime(job.fechaInicio)} />
        <Info label="Fin" value={formatDateTime(job.fechaFin)} />
        {job.detalle ? (
          <div className="md:col-span-2">
            <div className="text-xs font-semibold text-slate-500 uppercase">Detalle / Warnings</div>
            <pre className="mt-1 whitespace-pre-wrap text-sm text-slate-800 bg-slate-50 p-3 rounded-lg ring-1 ring-slate-200">
              {job.detalle}
            </pre>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-semibold text-slate-500 uppercase">{label}</div>
      <div className="mt-1 text-sm text-slate-800">{value}</div>
    </div>
  );
}
