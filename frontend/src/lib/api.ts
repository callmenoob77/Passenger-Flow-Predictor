// In dev: empty string → Vite proxy rewrites /api/* to backend.
// In prod: set VITE_API_BASE=https://your-backend.onrender.com (no trailing slash).
const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export const api = (path: string) =>
  API_BASE ? `${API_BASE}${path}` : `/api${path}`;
