import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { useUsuario, useUpdateUsuario } from '../hooks/useUsers';
import Modal from './shared/Modal';
import Input from './shared/Input';

export default function EditUserModal({ userId, onClose }: { userId: number; onClose: () => void }) {
  const { data, isLoading } = useUsuario(userId);
  const upd = useUpdateUsuario();

  const [rol, setRol] = useState<string>('administrador');
  const [contrasena, setContrasena] = useState<string>('');

  useEffect(() => {
    if (data) setRol(data.rol);
  }, [data]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await upd.mutateAsync({
        id: userId,
        body: { rol, contrasena: contrasena || undefined },
      });
      toast.success('Usuario actualizado.');
      onClose();
    } catch {}
  };

  return (
    <Modal title="Editar usuario" onClose={onClose}>
      {isLoading ? (
        <div className="p-4 text-white/80">Cargando...</div>
      ) : !data ? (
        <div className="p-4 text-white/80">No se encontró el usuario.</div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3">
          <div className="text-sm text-white/70">Correo: <span className="text-white">{data.correo}</span></div>

          <label className="block text-sm">
            <span className="mb-1 block text-white/80">Rol</span>
            <select
              className="w-full rounded-md border border-white/10 bg-white/5 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
              value={rol}
              onChange={(e) => setRol(e.target.value)}
            >
              <option value="administrador">Administrador</option>
              <option value="duenoDeEmpresa">Dueño de Empresa</option>
            </select>
          </label>

          <Input
            label="Nueva contraseña (opcional)"
            value={contrasena}
            onChange={setContrasena}
            type="password"
            required={false}
          />

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="rounded-md px-3 py-1.5 text-sm text-white/80 hover:bg-white/10">
              Cancelar
            </button>
            <button type="submit" className="rounded-md bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-600">
              Guardar cambios
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}
