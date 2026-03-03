import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { LayoutDashboard, Map, Users2, User, FileText, LogOut } from 'lucide-react';

export default function Layout({ children }) {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

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
                        <Users2 size={16} /> {isManager ? 'Team Overview' : 'Admin'}
                    </NavLink>
                )}
                <NavLink to="/resume" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                    <FileText size={16} /> Resume
                </NavLink>
                <NavLink to="/profile" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                    <User size={16} /> Profile
                </NavLink>

                <div className="spacer" />

                <div className="user-card">
                    <div className="name">{user?.display_name}</div>
                    <div className="role">Level {user?.level} · {user?.xp_balance} XP</div>
                </div>
                <button className="nav-link" onClick={doLogout} style={{ color: 'var(--danger)' }}>
                    <LogOut size={16} /> Logout
                </button>
            </nav>
            <main className="main-content">{children}</main>
        </div>
    );
}
