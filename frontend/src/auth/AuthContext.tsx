import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { authApi } from '../api/endpoints';
import type { User, LoginRequest, SignupRequest } from '../types';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (data: LoginRequest) => Promise<void>;
  signup: (data: SignupRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadUser = useCallback(async () => {
    const token = localStorage.getItem('finpilot_token');
    if (!token) {
      setIsLoading(false);
      return;
    }
    try {
      const userData = await authApi.me();
      setUser(userData);
    } catch {
      localStorage.removeItem('finpilot_token');
      localStorage.removeItem('finpilot_user');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  const login = async (data: LoginRequest) => {
    const tokens = await authApi.login(data);
    localStorage.setItem('finpilot_token', tokens.access_token);
    const userData = await authApi.me();
    setUser(userData);
    localStorage.setItem('finpilot_user', JSON.stringify(userData));
  };

  const signup = async (data: SignupRequest) => {
    await authApi.signup(data);
    // After signup, login automatically
    await login({ email: data.email, password: data.password });
  };

  const logout = useCallback(() => {
    localStorage.removeItem('finpilot_token');
    localStorage.removeItem('finpilot_user');
    setUser(null);
    window.location.href = '/login';
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        signup,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}

export default AuthContext;
