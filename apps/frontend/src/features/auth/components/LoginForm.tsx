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
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Inicia sesión</h2>
        <p className="card-subtitle">Accede con tus credenciales corporativas.</p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)}>
        <div className="form-group">
          <label className="label">Correo</label>
          <input
            type="email"
            className="input"
            placeholder="tucorreo@dominio.com"
            {...register('email')}
          />
          {errors.email && <p className="error">{errors.email.message}</p>}
        </div>

        <div className="form-group">
          <label className="label">Contraseña</label>
          <input
            type="password"
            className="input"
            placeholder="••••••••"
            {...register('password')}
          />
          {errors.password && <p className="error">{errors.password.message}</p>}
        </div>

        <button type="submit" disabled={isPending} className="button">
          {isPending ? 'Ingresando…' : 'Ingresar'}
        </button>
      </form>
    </div>
  );
}
