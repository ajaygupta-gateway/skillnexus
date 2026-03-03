import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authApi, userApi } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    const loadUser = useCallback(async () => {
        const token = localStorage.getItem('access_token');
        if (!token) { setLoading(false); return; }
        try {
            const { data } = await userApi.me();
            setUser(data);
        } catch {
            localStorage.clear();
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadUser(); }, [loadUser]);

    const login = async (email, password) => {
        const { data } = await authApi.login({ email, password });
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('refresh_token', data.refresh_token);
        await loadUser();
    };

    const register = async (payload) => {
        await authApi.register(payload);
        await login(payload.email, payload.password);
    };

    const logout = async () => {
        const rt = localStorage.getItem('refresh_token');
        try { await authApi.logout(rt); } catch { /* ignore */ }
        localStorage.clear();
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, loading, login, register, logout, reload: loadUser }}>
            {children}
        </AuthContext.Provider>
    );
}

export const useAuth = () => useContext(AuthContext);
