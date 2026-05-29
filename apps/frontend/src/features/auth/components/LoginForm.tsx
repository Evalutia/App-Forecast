import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import type { LoginRequest } from '../types/auth';
import { useLogin } from '../hooks/useLogin';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

const schema = z.object({
  email:    z.string().email('Correo inválido'),
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
    } catch (err: unknown) {
      const msg = (err as { normalizedMessage?: string })?.normalizedMessage;
      toast.error(msg ?? 'No se pudo iniciar sesión');
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <div className="login-form-group">
        <label className="login-label">Correo</label>
        <input
          type="email"
          className="login-input"
          placeholder="tucorreo@dominio.com"
          {...register('email')}
        />
        {errors.email && <p className="login-error">{errors.email.message}</p>}
      </div>

      <div className="login-form-group">
        <label className="login-label">Contraseña</label>
        <input
          type="password"
          className="login-input"
          placeholder="••••••••"
          {...register('password')}
        />
        {errors.password && <p className="login-error">{errors.password.message}</p>}
      </div>

      <button type="submit" disabled={isPending} className="login-btn">
        {isPending ? 'Ingresando…' : 'Ingresar'}
      </button>
    </form>
  );
}
