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
        <p className="muted">Cargando...</p>
      ) : !data ? (
        <p className="muted">No se encontró el usuario.</p>
      ) : (
        <form onSubmit={onSubmit}>
          <div style={{ marginBottom: '.85rem', fontSize: '.9rem', color: '#6b7280' }}>
            Correo: <strong style={{ color: 'var(--emerald-950)' }}>{data.correo}</strong>
          </div>

          <div className="form-row" style={{ alignItems: 'flex-start', marginBottom: '.85rem' }}>
            <label className="label" style={{ textAlign: 'left' }}>Rol</label>
            <select
              className="select"
              value={rol}
              onChange={(e) => setRol(e.target.value)}
            >
              <option value="administrador">Administrador</option>
              <option value="duenoDeEmpresa">Dueño de Empresa</option>
            </select>
          </div>

          <Input
            label="Nueva contraseña (opcional)"
            value={contrasena}
            onChange={setContrasena}
            type="password"
            required={false}
          />

          <div className="filters-actions" style={{ justifyContent: 'flex-end', marginTop: '1.25rem' }}>
            <button type="button" className="button button-ghost" onClick={onClose}>Cancelar</button>
            <button type="submit" className="button" disabled={upd.isPending}>
              {upd.isPending ? 'Guardando...' : 'Guardar cambios'}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}
