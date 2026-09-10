import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "/api",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("school_access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Endpoints that must never trigger a refresh-and-retry (refreshing itself,
// or logging in, would otherwise recurse).
const REFRESH_EXEMPT = ["/token/", "/token/refresh/"];

let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem("school_refresh_token");
  if (!refreshToken) return null;
  try {
    const response = await axios.post(`${api.defaults.baseURL}/token/refresh/`, { refresh: refreshToken });
    const newAccessToken: string = response.data.access;
    localStorage.setItem("school_access_token", newAccessToken);
    return newAccessToken;
  } catch {
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    const isExempt = REFRESH_EXEMPT.some((path) => config?.url?.includes(path));

    if (error.response?.status === 401 && config && !config._retried && !isExempt) {
      config._retried = true;
      refreshInFlight ??= refreshAccessToken().finally(() => {
        refreshInFlight = null;
      });
      const newAccessToken = await refreshInFlight;
      if (newAccessToken) {
        config.headers.Authorization = `Bearer ${newAccessToken}`;
        return api(config);
      }
      localStorage.removeItem("school_access_token");
      localStorage.removeItem("school_refresh_token");
      localStorage.removeItem("school_user");
      window.dispatchEvent(new Event("school:unauthorized"));
    }
    return Promise.reject(error);
  },
);
