import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, tokenStore } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=checking, false=guest, obj=auth

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      return data;
    } catch {
      setUser(false);
      return false;
    }
  }, []);

  useEffect(() => {
    if (!tokenStore.access) {
      setUser(false);
      return;
    }
    refresh();
  }, [refresh]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    if (data.access_token) tokenStore.set(data.access_token, data.refresh_token);
    setUser(data);
    return data;
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch {}
    tokenStore.clear();
    setUser(false);
  };

  const hasRole = (...roles) => user && (roles.length === 0 || roles.includes(user.role));

  return (
    <AuthContext.Provider value={{ user, setUser, login, logout, refresh, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
