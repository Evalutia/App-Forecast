import { toast } from 'sonner';
import type { UsuarioRow } from '../types/users';
import { useBorrarAdministradorPorCorreo } from '../hooks/useUsers';

export default function RowActions({
  user,
  onEdit,
}: {
  user: UsuarioRow;
  onEdit: () => void;
}) {
  const borrarAdmin = useBorrarAdministradorPorCorreo();

  const canDelete = user.rol === 'administrador'; // backend solo expone delete por correo para admins

  const handleDelete = async () => {
    if (!confirm(`¿Eliminar administrador ${user.correo}?`)) return;
    try {
      await borrarAdmin.mutateAsync(user.correo);
      toast.success('Administrador eliminado.');
    } catch (e: any) {
      // el interceptor ya muestra el error; opcionalmente:
      if (!e?.normalizedMessage) toast.error('No se pudo eliminar.');
    }
  };

  return (
    <div className="flex justify-end gap-2">
      <button
        onClick={onEdit}
        className="rounded-md bg-white/10 px-3 py-1.5 text-xs font-medium text-white hover:bg-white/20"
      >
        Cambiar rol/contraseña
      </button>
      {canDelete && (
        <button
          onClick={handleDelete}
          className="rounded-md bg-red-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600"
        >
          Eliminar
        </button>
      )}
    </div>
  );
}
