import axios from "axios";
import { useEffect, useState } from "react";

// Produção: vazio => mesma origem (/api). Preview: URL externa do backend.
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

const ACCESS_KEY = "scarvel_token";
const REFRESH_KEY = "nx_refresh_token";

export const tokenStore = {
  get access() { return localStorage.getItem(ACCESS_KEY); },
  get refresh() { return localStorage.getItem(REFRESH_KEY); },
  set(access, refresh) {
    if (access) localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const t = tokenStore.access;
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

let refreshing = null;
api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    if (
      error.response?.status === 401 &&
      !original._retry &&
      !original.url.includes("/auth/")
    ) {
      original._retry = true;
      try {
        refreshing =
          refreshing ||
          api.post("/auth/refresh", { refresh_token: tokenStore.refresh });
        const { data } = await refreshing;
        refreshing = null;
        if (data?.access_token) tokenStore.set(data.access_token, data.refresh_token);
        original.headers.Authorization = `Bearer ${tokenStore.access}`;
        return api(original);
      } catch (e) {
        refreshing = null;
      }
    }
    return Promise.reject(error);
  }
);

export function formatApiErrorDetail(detail) {
  if (detail == null) return "Algo deu errado. Tente novamente.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export function wsUrl() {
  const base = BACKEND_URL
    ? BACKEND_URL.replace(/^http/, "ws")
    : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  const t = tokenStore.access;
  return `${base}/api/ws${t ? `?token=${t}` : ""}`;
}

let infoPromise = null;
export function useAppInfo() {
  const [info, setInfo] = useState(null);
  useEffect(() => {
    infoPromise = infoPromise || api.get("/version").then((r) => r.data).catch(() => { infoPromise = null; return null; });
    infoPromise.then(setInfo);
  }, []);
  return info;
}
