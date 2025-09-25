import type { UsuarioRow } from '../types/users';
import RowActions from './UserTableRowActions';

export default function UserTable({
  rows,
  isLoading,
  onEdit,
}: {
  rows: UsuarioRow[];
  isLoading?: boolean;
  onEdit: (id: number) => void;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-white/5">
      <table className="min-w-full divide-y divide-white/10">
        <thead className="bg-white/5">
          <tr>
            <Th>Id</Th>
            <Th>Correo</Th>
            <Th>Rol</Th>
            <Th className="text-right">Acciones</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/10">
          {isLoading ? (
            <tr><td colSpan={4} className="p-4 text-center text-white/70">Cargando...</td></tr>
          ) : rows.length === 0 ? (
            <tr><td colSpan={4} className="p-4 text-center text-white/70">Sin resultados</td></tr>
          ) : (
            rows.map((u) => (
              <tr key={u.id} className="hover:bg-white/[0.04]">
                <Td>{u.id}</Td>
                <Td className="font-medium">{u.correo}</Td>
                <Td>
                  <span className="rounded-md bg-emerald-700/30 px-2 py-0.5 text-xs text-emerald-100">
                    {u.rol}
                  </span>
                </Td>
                <Td className="text-right">
                  <RowActions user={u} onEdit={() => onEdit(u.id)} />
                </Td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function Th({ children, className = '' }: any) {
  return (
    <th className={`px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-white/70 ${className}`}>
      {children}
    </th>
  );
}
function Td({ children, className = '' }: any) {
  return <td className={`px-4 py-3 text-sm text-white ${className}`}>{children}</td>;
}
