import { useState } from 'react';
import { toast } from 'sonner';
import { useCrearDuenoEmpresa } from '../hooks/useUsers';

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
      <form onSubmit={onSubmit} className="space-y-3">
        <Input label="Correo" value={correo} onChange={setCorreo} type="email" />
        <Input label="Contraseña" value={contrasena} onChange={setContrasena} type="password" />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="rounded-md px-3 py-1.5 text-sm text-white/80 hover:bg-white/10">
            Cancelar
          </button>
          <button type="submit" className="rounded-md bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-600">
            Crear
          </button>
        </div>
      </form>
    </Modal>
  );
}

import Modal from './shared/Modal';
import Input from './shared/Input';
