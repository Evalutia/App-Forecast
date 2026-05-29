import LoginForm from '../components/LoginForm';
import '../../../styles/login.css';

export default function LoginPage() {
  return (
    <div className="login-page">
      <div className="login-grid" />
      <div className="login-glow" />
      <div className="login-card">
        <span className="login-brand">Evalutia</span>
        <h1 className="login-title">Portal de acceso</h1>
        <p className="login-subtitle">
          Iniciá sesión para continuar con tus reportes y predicciones.
        </p>
        <LoginForm />
        <div className="login-footer">Evalutia · Acceso corporativo</div>
      </div>
    </div>
  );
}
