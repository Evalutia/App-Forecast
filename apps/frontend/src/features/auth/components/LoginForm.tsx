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
    <div className="w-full max-w-md rounded-3xl border border-emerald-100/40 bg-white/95 p-10 shadow-2xl shadow-emerald-950/20 backdrop-blur">
      <div className="mb-8 space-y-2 text-center">
        <h2 className="text-3xl font-semibold text-emerald-950">Inicia sesión</h2>
        <p className="text-sm text-emerald-900/70">Accede con tus credenciales corporativas.</p>
      </div>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        <div className="space-y-2">
          <label className="block text-sm font-medium uppercase tracking-wide text-emerald-900/80">
            Correo
          </label>
          <input
            type="email"
            className="w-full rounded-xl border border-emerald-200/60 bg-white px-4 py-3 text-emerald-950 shadow-sm transition focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-400/50"
            placeholder="tucorreo@dominio.com"
            {...register('email')}
          />
          {errors.email && <p className="text-sm text-red-600">{errors.email.message}</p>}
        </div>
        <div className="space-y-2">
          <label className="block text-sm font-medium uppercase tracking-wide text-emerald-900/80">
            Contraseña
          </label>
          <input
            type="password"
            className="w-full rounded-xl border border-emerald-200/60 bg-white px-4 py-3 text-emerald-950 shadow-sm transition focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-400/50"
            placeholder="••••••••"
            {...register('password')}
          />
          {errors.password && <p className="text-sm text-red-600">{errors.password.message}</p>}
        </div>
        <button
          type="submit"
          disabled={isPending}
          className="w-full rounded-xl bg-emerald-900 px-4 py-3 text-sm font-semibold uppercase tracking-wide text-white transition hover:bg-emerald-800 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isPending ? 'Ingresando…' : 'Ingresar'}
        </button>
      </form>
    </div>
  );
}