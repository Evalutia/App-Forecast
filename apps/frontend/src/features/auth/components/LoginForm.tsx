import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import type { LoginRequest } from '../types/auth';
import { useLogin } from '../hooks/useLogin';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

const schema = z.object({
  email: z.string().email('Correo inválido'),
  password: z.string().min(8, 'Mínimo 8 caracteres'),
});
type FormValues = z.infer<typeof schema>;

export default function LoginForm() {
  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    resolver: zodResolver(schema),
  });
  const { mutateAsync, isPending } = useLogin();
  const navigate = useNavigate();

  const onSubmit = async (values: FormValues) => {
    try {
      await mutateAsync(values as LoginRequest);
      toast.success('Sesión iniciada');
      navigate('/');
    } catch (err: any) {
      toast.error(err?.normalizedMessage ?? 'No se pudo iniciar sesión');
    }
  };

  return (
    <div className="mx-auto max-w-sm p-6 bg-white rounded shadow">
      <h1 className="text-xl font-semibold mb-4">Ingresar</h1>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">Correo</label>
          <input
            type="email"
            className="w-full border rounded px-3 py-2"
            placeholder="tucorreo@dominio.com"
            {...register('email')}
          />
          {errors.email && <p className="text-sm text-red-600 mt-1">{errors.email.message}</p>}
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Contraseña</label>
          <input
            type="password"
            className="w-full border rounded px-3 py-2"
            {...register('password')}
          />
          {errors.password && <p className="text-sm text-red-600 mt-1">{errors.password.message}</p>}
        </div>
        <button
          type="submit"
          disabled={isPending}
          className="w-full py-2 rounded bg-black text-white disabled:opacity-50"
        >
          {isPending ? 'Ingresando…' : 'Ingresar'}
        </button>
      </form>
    </div>
  );
}
