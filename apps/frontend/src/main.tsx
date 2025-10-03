import React from 'react';
import ReactDOM from 'react-dom/client';
import AppRoutes from './routes/AppRoutes';
import './index.css';
import './styles/login.css';
import './styles/home.css';
import './styles/sales.css';
import './styles/jobs.css';
import './styles/predicciones.css';


ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppRoutes />
  </React.StrictMode>
);
