import LoginForm from '../components/LoginForm';

export default function LoginPage() {
  return (
    <div className="login-page">
      <div className="login-wrapper">
        <div>
          {/* Título de marca arriba */}
          <div className="login-brand">EVALUTIA</div>

          <h1 className="login-title">Portal de acceso seguro</h1>
          <p className="login-subtitle">
            Inicia sesión para continuar con tus evaluaciones y reportes. Un entorno minimalista
            y diseñado para mantener tu enfoque.
          </p>
        </div>

        <LoginForm />
      </div>
    </div>
  );
}
