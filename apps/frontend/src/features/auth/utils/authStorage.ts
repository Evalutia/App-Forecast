import type { User } from '../types/auth';

const KEY = 'auth';

export function saveAuth(token: string, user: User) {
  localStorage.setItem(`${KEY}.token`, token);
  localStorage.setItem(`${KEY}.user`, JSON.stringify(user ?? {}));
}

export function getToken(): string | null {
  return localStorage.getItem(`${KEY}.token`);
}

export function getUser(): User | null {
  const raw = localStorage.getItem(`${KEY}.user`);
  if (!raw) return null;
  try { return JSON.parse(raw) as User; } catch { return null; }
}

export function clearAuth() {
  localStorage.removeItem(`${KEY}.token`);
  localStorage.removeItem(`${KEY}.user`);
}

export function isTokenExpired(_token?: string | null): boolean {
  // Si después querés, decodificamos y validamos exp; por ahora simple.
  return false;
}
