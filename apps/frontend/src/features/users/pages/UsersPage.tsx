import { useMemo, useState } from 'react';
import { useUsuariosList } from '../hooks/useUsers';
import UserTable from '../components/UserTable';
import Pagination from '../components/Pagination';
import AddAdminModal from '../components/AddAdminModal';
import AddOwnerModal from '../components/AddOwnerModal';
import EditUserModal from '../components/EditUserModal';
import BackToDashboardButton from '../components/BackToDashboardButton';

export default function UsersPage() {
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [correo, setCorreo] = useState<string>('');
  const [rol, setRol] = useState<string>('');

  const { data, isLoading } = useUsuariosList({
    page,
    pageSize,
    correo: correo || undefined,
    rol: rol || undefined,
  });

  const [showAddAdmin, setShowAddAdmin] = useState(false);
  const [showAddOwner, setShowAddOwner] = useState(false);
  const [editUserId, setEditUserId] = useState<number | null>(null);

  const total = data?.total ?? 0;
  const items = data?.items ?? [];

  // Reset page al cambiar filtros
  const filtersKey = useMemo(() => `${correo}|${rol}`, [correo, rol]);

  return (
    <div className="mx-auto max-w-6xl p-6">
        <div className="mb-6 flex items-center justify-between">
            <h1 className="text-2xl font-semibold text-white">Administración de usuarios</h1>
            <div className="flex items-center gap-2">
                <BackToDashboardButton />
                <button
                    onClick={() => setShowAddAdmin(true)}
                    className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-600"
                >
                    Agregar Administrador
                </button>
                <button
                    onClick={() => setShowAddOwner(true)}
                    className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-600"
                >
                    Agregar Dueño de Empresa
                </button>
            </div>
        </div>

      {/* Filtros */}
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <input
          className="rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          placeholder="Buscar por correo..."
          value={correo}
          onChange={(e) => { setCorreo(e.target.value); setPage(1); }}
        />
        <select
          className="rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
          value={rol}
          onChange={(e) => { setRol(e.target.value); setPage(1); }}
        >
          <option value="">Todos los roles</option>
          <option value="administrador">Administrador</option>
          <option value="duenoDeEmpresa">Dueño de Empresa</option>
        </select>
      </div>

      <UserTable
        key={filtersKey} // ayuda a resetear selección al cambiar filtros
        rows={items}
        isLoading={isLoading}
        onEdit={(id) => setEditUserId(id)}
      />

      <div className="mt-4">
        <Pagination
          page={page}
          pageSize={pageSize}
          total={total}
          onPageChange={setPage}
        />
      </div>

      {/* Modales */}
      {showAddAdmin && <AddAdminModal onClose={() => setShowAddAdmin(false)} />}
      {showAddOwner && <AddOwnerModal onClose={() => setShowAddOwner(false)} />}
      {editUserId != null && (
        <EditUserModal userId={editUserId} onClose={() => setEditUserId(null)} />
      )}
    </div>
  );
}
