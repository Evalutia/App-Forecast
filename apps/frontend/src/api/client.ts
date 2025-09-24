import axios from 'axios';

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

api.interceptors.response.use(
  (res) => res,
  (error) => {
    const data = error?.response?.data;
    const status = error?.response?.status;

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

    error.status = status;
    error.normalizedMessage = msg;
    error.message = msg; 

    return Promise.reject(error);
  }
);

export default api;
