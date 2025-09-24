import LoginForm from '../components/LoginForm';

export default function LoginPage() {
  return (
    <div className="min-h-dvh bg-gradient-to-br from-emerald-950 via-emerald-900 to-emerald-950 px-6 py-16">
      <div className="mx-auto flex max-w-5xl flex-col items-center justify-center gap-10 text-center text-white">
        <div className="space-y-4">
          <span className="rounded-full border border-white/10 bg-white/10 px-4 py-1 text-xs font-medium uppercase tracking-[0.3em] text-emerald-100">
            Evalutia
          </span>
          <h1 className="text-4xl font-semibold sm:text-5xl">Portal de acceso seguro</h1>
          <p className="text-lg text-emerald-100/90">
            Inicia sesión para continuar con tus evaluaciones y reportes. Un entorno minimalista
            y diseñado para mantener tu enfoque.
          </p>
        </div>
        <LoginForm />
      </div>
    </div>
  );
}
