import axios from 'axios';
import { toast } from 'sonner';
import { clearAuth } from '../features/auth/utils/authStorage';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, '') ?? 'http://localhost:8081',
  withCredentials: false,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth.token');
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let lastMsg = '';
let lastAt = 0;

api.interceptors.response.use(
  (res) => res,
  (error) => {
    const data = error?.response?.data;
    const status = error?.response?.status;
    const isCanceled =
          axios.isCancel?.(error) ||
          error?.code === 'ERR_CANCELED' ||
          error?.name === 'CanceledError' ||
          /aborted|canceled/i.test(String(error?.message));

    if (isCanceled) {
      return Promise.reject(error);
    }

    let msg =
      data?.mensaje ??
      data?.Mensaje ??
      data?.message ??
      data?.title ??
      data?.detail ??
      (status === 401
        ? 'Sesión expirada. Iniciá sesión de nuevo.'
        : status === 403
        ? 'No tenés permisos para esta acción.'
        : status
        ? `Error ${status}`
        : 'No se pudo conectar con el servidor');

    const errs = data?.errores || data?.errors;
    if (errs && typeof errs === 'object') {
      const detalles = Object.entries(errs)
        .flatMap(([k, arr]) => (Array.isArray(arr) ? arr : [arr]).map((x: any) => `${k}: ${String(x)}`))
        .join(' · ');
      if (detalles) msg = `${msg}\n${detalles}`;
    }

    // toast centralizado (evitar duplicados muy seguidos)
    const now = Date.now();
    if (msg !== lastMsg || now - lastAt > 1200) {
      toast.error(msg);
      lastMsg = msg;
      lastAt = now;
    }

    // manejar 401 (opcional): limpiar sesión y mandar a /login
    if (status === 401) {
      clearAuth();
      // si querés: window.location.assign('/login');
    }

    error.status = status;
    error.normalizedMessage = msg;
    error.message = msg;

    return Promise.reject(error);
  }
);

export default api;