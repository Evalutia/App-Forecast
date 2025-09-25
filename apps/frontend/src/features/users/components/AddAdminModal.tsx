import { useState } from 'react';
import { toast } from 'sonner';
import { useCrearAdministrador } from '../hooks/useUsers';

export default function AddAdminModal({ onClose }: { onClose: () => void }) {
  const [correo, setCorreo] = useState('');
  const [contrasena, setContrasena] = useState('');
  const crear = useCrearAdministrador();

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await crear.mutateAsync({ correo, contrasena });
      toast.success('Administrador creado.');
      onClose();
    } catch {}
  };

  return (
    <Modal title="Agregar Administrador" onClose={onClose}>
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

function Modal({ title, onClose, children }: any) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-emerald-950 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">{title}</h3>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-white/70 hover:bg-white/10">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}
function Input({ label, value, onChange, type = 'text' }: any) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-white/80">{label}</span>
      <input
        type={type}
        className="w-full rounded-md border border-white/10 bg-white/5 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required
      />
    </label>
  );
}
