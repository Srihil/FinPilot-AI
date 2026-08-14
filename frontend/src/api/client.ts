import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';

// In dev, use '' (relative URL) so Vite proxy forwards /api/* to the backend
// In production, set VITE_API_URL to the deployed backend URL
const BASE_URL = import.meta.env.VITE_API_URL || '';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Request interceptor - attach auth token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('finpilot_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - handle auth errors
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('finpilot_token');
      localStorage.removeItem('finpilot_user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
