// Backend base URL. Set VITE_API_URL in a .env file (see .env.example).
// Falls back to the local dev backend so `npm run dev` works out of the box.
export const API_BASE_URL =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/+$/, '') ||
  'http://localhost:8000';

export const ACCESS_TOKEN_KEY = 'access_token';
export const THEME_KEY = 'ui-theme';
