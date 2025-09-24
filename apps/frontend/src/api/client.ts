import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, '') ?? 'http://localhost:8080',
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
    error.normalizedMessage = data?.message || data?.title || data?.detail || error.message || 'Error desconocido';
    error.status = error?.response?.status;
    return Promise.reject(error);
  }
);

export default api;
