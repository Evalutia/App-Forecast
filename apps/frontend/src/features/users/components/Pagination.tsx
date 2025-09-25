export default function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (p: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="flex items-center justify-between text-sm text-white/80">
      <span>
        Página <b className="text-white">{page}</b> de <b className="text-white">{totalPages}</b>
      </span>
      <div className="flex gap-2">
        <button
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 disabled:opacity-50"
        >
          Anterior
        </button>
        <button
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 disabled:opacity-50"
        >
          Siguiente
        </button>
      </div>
    </div>
  );
}
