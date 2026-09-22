import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { User } from '../types';
import { authApi, getErrorMessage } from '../lib/api';
import { ACCESS_TOKEN_KEY } from '../config';

interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(ACCESS_TOKEN_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let cancelled = false;
    async function hydrate() {
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const me = await authApi.me();
        if (!cancelled) setUser(me);
      } catch {
        // Invalid/expired token — the axios interceptor already clears it.
        if (!cancelled) {
          localStorage.removeItem(ACCESS_TOKEN_KEY);
          setToken(null);
          setUser(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void hydrate();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const login = useCallback(async (email: string, password: string) => {
    const payload = await authApi.login(email, password).catch((err: unknown) => {
      throw new Error(getErrorMessage(err, 'Login failed'));
    });
    localStorage.setItem(ACCESS_TOKEN_KEY, payload.access_token);
    setToken(payload.access_token);
    setUser(payload.user);
  }, []);

  const register = useCallback(async (name: string, email: string, password: string) => {
    const payload = await authApi.register(name, email, password).catch((err: unknown) => {
      throw new Error(getErrorMessage(err, 'Registration failed'));
    });
    localStorage.setItem(ACCESS_TOKEN_KEY, payload.access_token);
    setToken(payload.access_token);
    setUser(payload.user);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, token, loading, login, register, logout }),
    [user, token, loading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
