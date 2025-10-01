import { Link, useParams } from 'react-router-dom';
import JobDetailPanel from '../../jobs/components/JobDetailPanel';
import JobPrediccionesLink from '../../jobs/components/JobPrediccionesLink';

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);

  return (
    <div className="mx-auto max-w-4xl p-4 md:p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Detalle del Job</h1>
        <Link to="/jobs" className="text-blue-600 hover:text-blue-700 hover:underline">
          ← Volver a Jobs
        </Link>
      </div>

      {Number.isNaN(jobId) ? (
        <div className="rounded-xl ring-1 ring-slate-200 bg-white p-6 text-slate-600">
          ID inválido.
        </div>
      ) : (
        <>
          <JobDetailPanel jobId={jobId} />
          <div className="mt-4">
            <JobPrediccionesLink jobId={jobId} />
          </div>
        </>
      )}
    </div>
  );
}
