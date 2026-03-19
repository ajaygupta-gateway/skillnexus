import { useState, useEffect } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { LayoutDashboard, Map, Users2, User, FileText, LogOut, Moon, Sun } from 'lucide-react';

export default function Layout({ children }) {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const [theme, setTheme] = useState(localStorage.getItem('theme') || 'dark');

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }, [theme]);

    const toggleTheme = () => {
        setTheme(prev => prev === 'dark' ? 'light' : 'dark');
    };

    const doLogout = async () => { await logout(); navigate('/login'); };

    const isAdmin = user?.role === 'admin';
    const isManager = user?.role === 'manager';

    return (
        <div className="app-shell">
            <nav className="sidebar">
                <div className="brand">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" /></svg>
                    SkillNexus
                </div>

                <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                    <LayoutDashboard size={16} /> Dashboard
                </NavLink>
                <NavLink to="/roadmaps" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                    <Map size={16} /> Roadmaps
                </NavLink>
                {(isAdmin || isManager) && (
                    <NavLink to="/admin" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                        <Users2 size={16} /> {isManager ? 'Team Overview' : 'Control Center'}
                    </NavLink>
                )}
                <NavLink to="/resume" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                    <FileText size={16} /> Resume
                </NavLink>
                <NavLink to="/profile" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                    <User size={16} /> Profile
                </NavLink>

                <div className="spacer" />

                <button className="nav-link" onClick={toggleTheme} style={{ marginBottom: '8px' }}>
                    {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
                    {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
                </button>

                <div className="user-card" style={{ display: 'flex', flexDirection: 'row', alignItems: 'flex-start', gap: '8px' }}>
                    <div className="name">{user?.display_name}</div>
                    <div className="role">
                        {isAdmin || isManager
                            ? <span className="badge badge-primary" style={{ fontSize: 11}}>{user?.role.toUpperCase()}</span>
                            : <>Level {user?.level} · {(user?.xp_balance ?? 0) % 500} XP</>
                        }
                    </div>
                </div>
                <button className="nav-link" onClick={doLogout} style={{ color: 'var(--danger)' }}>
                    <LogOut size={16} /> Logout
                </button>
            </nav>
            <main className="main-content">{children}</main>
        </div>
    );
}