import { useState } from 'react';
import { toast } from 'sonner';
import { useCrearDuenoEmpresa } from '../hooks/useUsers';
import Modal from './shared/Modal';
import Input from './shared/Input';

export default function AddOwnerModal({ onClose }: { onClose: () => void }) {
  const [correo, setCorreo] = useState('');
  const [contrasena, setContrasena] = useState('');
  const crear = useCrearDuenoEmpresa();

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await crear.mutateAsync({ correo, contrasena });
      toast.success('Dueño de Empresa creado.');
      onClose();
    } catch {}
  };

  return (
    <Modal title="Agregar Dueño de Empresa" onClose={onClose}>
      <form onSubmit={onSubmit}>
        <Input label="Correo" value={correo} onChange={setCorreo} type="email" />
        <Input label="Contraseña" value={contrasena} onChange={setContrasena} type="password" />
        <div className="filters-actions" style={{ justifyContent: 'flex-end', marginTop: '1.25rem' }}>
          <button type="button" className="button button-ghost" onClick={onClose}>Cancelar</button>
          <button type="submit" className="button" disabled={crear.isPending}>
            {crear.isPending ? 'Creando...' : 'Crear'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
