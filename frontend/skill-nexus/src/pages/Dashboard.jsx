import { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { userApi, adminApi, roadmapApi } from '../api/client';
import { Trophy, Zap, Flame, BarChart2, Users, Map, UserPlus, Activity, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  LEARNER DASHBOARD — XP, streak, leaderboard, recent events               */
/* ═══════════════════════════════════════════════════════════════════════════ */
function LearnerDashboard({ user }) {
    const [leaderboard, setLeaderboard] = useState([]);
    const [txns, setTxns] = useState([]);

    useEffect(() => {
        userApi.leaderboard().then(r => setLeaderboard(r.data.entries || [])).catch(() => { });
        userApi.transactions().then(r => setTxns(r.data.slice(0, 10))).catch(() => { });
    }, []);

    const xpToNext = 500 - (user?.xp_balance % 500);
    const pct = Math.round(((user?.xp_balance % 500) / 500) * 100);

    return (
        <>
            <div className="stats-row">
                <div className="stat-card">
                    <div className="value" style={{ color: 'var(--warn)' }}><Zap size={18} style={{ verticalAlign: 'middle', marginRight: 4 }} />{user?.xp_balance ?? 0}</div>
                    <div className="label">Total XP</div>
                </div>
                <div className="stat-card">
                    <div className="value" style={{ color: 'var(--primary-h)' }}>{user?.level ?? 1}</div>
                    <div className="label">Level</div>
                </div>
                <div className="stat-card">
                    <div className="value" style={{ color: 'var(--success)' }}><Flame size={18} style={{ verticalAlign: 'middle', marginRight: 4 }} />{user?.streak_count ?? 0}</div>
                    <div className="label">Day Streak</div>
                </div>
                <div className="stat-card">
                    <div className="value" style={{ color: 'var(--muted)', fontSize: '1rem', marginTop: 4 }}>{user?.role}</div>
                    <div className="label">Role</div>
                </div>
            </div>

            {/* XP Progress */}
            <div className="card mb-4" style={{ marginBottom: 20 }}>
                <div className="flex justify-between items-center" style={{ marginBottom: 8 }}>
                    <span style={{ fontWeight: 600 }}>XP to Level {(user?.level ?? 1) + 1}</span>
                    <span className="text-muted">{xpToNext} XP remaining</span>
                </div>
                <div className="progress-bar">
                    <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                {/* Leaderboard */}
                <div className="card">
                    <h3 style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <Trophy size={16} color="var(--warn)" /> Weekly Leaderboard
                    </h3>
                    {leaderboard.length === 0
                        ? <p className="text-muted" style={{ fontSize: 13 }}>No data yet.</p>
                        : <div className="table-wrap" style={{ border: 'none' }}>
                            <table>
                                <thead><tr><th>#</th><th>Name</th><th>XP</th><th>Level</th></tr></thead>
                                <tbody>
                                    {leaderboard.map(e => (
                                        <tr key={e.user_id} className="leaderboard-row">
                                            <td>{e.rank}</td>
                                            <td style={{ fontWeight: e.user_id === user?.id ? 600 : 400 }}>{e.display_name}{e.user_id === user?.id && ' (you)'}</td>
                                            <td>{e.xp_earned}</td>
                                            <td>{e.level}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    }
                </div>

                {/* Recent XP */}
                <div className="card">
                    <h3 style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <BarChart2 size={16} color="var(--primary-h)" /> Recent XP Events
                    </h3>
                    {txns.length === 0
                        ? <p className="text-muted" style={{ fontSize: 13 }}>No transactions yet.</p>
                        : <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {txns.map(t => (
                                <div key={t.id} className="flex justify-between items-center" style={{ padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                                    <div>
                                        <div style={{ fontWeight: 500, fontSize: 13 }}>{t.description || t.event_type}</div>
                                        <div className="text-muted" style={{ fontSize: 11 }}>{new Date(t.created_at).toLocaleDateString()}</div>
                                    </div>
                                    <span className="badge badge-warn">+{t.amount} XP</span>
                                </div>
                            ))}
                        </div>
                    }
                </div>
            </div>
        </>
    );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  ADMIN DASHBOARD — Platform overview, quick actions, recent activity       */
/* ═══════════════════════════════════════════════════════════════════════════ */
function AdminDashboard({ user }) {
    const navigate = useNavigate();
    const [stats, setStats] = useState(null);
    const [assignments, setAssignments] = useState([]);
    const [requests, setRequests] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const load = async () => {
            try {
                const [dash, asgn, reqs] = await Promise.all([
                    adminApi.dashboard(),
                    adminApi.getAssignments({ page_size: 5 }),
                    adminApi.getRoadmapRequests(),
                ]);
                setStats(dash.data?.stats);
                setAssignments(asgn.data?.items || []);
                setRequests((reqs.data || []).filter(r => r.status === 'pending'));
            } catch { /* noop */ }
            finally { setLoading(false); }
        };
        load();
    }, []);

    if (loading) return <div className="loading-center"><div className="spinner" /></div>;

    return (
        <>
            {/* Platform Stats */}
            {stats && (
                <div className="stats-row" style={{ marginBottom: 24 }}>
                    <div className="stat-card">
                        <div className="value" style={{ color: 'var(--primary-h)' }}><Users size={18} style={{ verticalAlign: 'middle', marginRight: 6 }} />{stats.total_users}</div>
                        <div className="label">Total Users</div>
                    </div>
                    <div className="stat-card">
                        <div className="value" style={{ color: 'var(--warn)' }}><Map size={18} style={{ verticalAlign: 'middle', marginRight: 6 }} />{stats.total_roadmaps}</div>
                        <div className="label">Roadmaps</div>
                    </div>
                    <div className="stat-card">
                        <div className="value" style={{ color: 'var(--success)' }}><UserPlus size={18} style={{ verticalAlign: 'middle', marginRight: 6 }} />{stats.total_assignments}</div>
                        <div className="label">Active Assignments</div>
                    </div>
                    <div className="stat-card">
                        <div className="value" style={{ color: 'var(--primary)' }}>{stats.avg_completion_percentage?.toFixed(0)}%</div>
                        <div className="label">Avg Completion</div>
                    </div>
                </div>
            )}

            {/* Quick Actions */}
            <div className="card" style={{ marginBottom: 20, padding: '16px 20px' }}>
                <h3 style={{ marginBottom: 14, fontSize: 15 }}>⚡ Quick Actions</h3>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    <button className="btn btn-ghost btn-sm" onClick={() => navigate('/roadmaps')}>
                        <Map size={14} /> Manage Roadmaps
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={() => navigate('/admin')}>
                        <Users size={14} /> Assignments & Analytics
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={() => navigate('/resume')}>
                        <Activity size={14} /> Resume Analysis
                    </button>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                {/* Recent Assignments */}
                <div className="card">
                    <div className="flex justify-between items-center" style={{ marginBottom: 14 }}>
                        <h3 style={{ display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
                            <UserPlus size={16} color="var(--primary-h)" /> Recent Assignments
                        </h3>
                        <button className="btn btn-ghost btn-sm" style={{ fontSize: 12 }} onClick={() => navigate('/admin')}>
                            View All <ArrowRight size={12} />
                        </button>
                    </div>
                    {assignments.length === 0
                        ? <p className="text-muted" style={{ fontSize: 13 }}>No assignments yet.</p>
                        : <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {assignments.map(a => (
                                <div key={a.id} className="flex justify-between items-center" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                                    <div>
                                        <div style={{ fontWeight: 500, fontSize: 13 }}>{a.user_display_name || a.user_id}</div>
                                        <div className="text-muted" style={{ fontSize: 11 }}>{a.roadmap_title || a.roadmap_id}</div>
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <div className="progress-bar" style={{ width: 60 }}>
                                            <div className="progress-bar-fill" style={{ width: `${a.completion_percentage || 0}%` }} />
                                        </div>
                                        <span style={{ fontSize: 11, color: 'var(--muted)' }}>{(a.completion_percentage || 0).toFixed(0)}%</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    }
                </div>

                {/* Pending Requests */}
                <div className="card">
                    <div className="flex justify-between items-center" style={{ marginBottom: 14 }}>
                        <h3 style={{ display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
                            <BarChart2 size={16} color="var(--warn)" /> Pending Roadmap Requests
                        </h3>
                        <button className="btn btn-ghost btn-sm" style={{ fontSize: 12 }} onClick={() => navigate('/admin')}>
                            View All <ArrowRight size={12} />
                        </button>
                    </div>
                    {requests.length === 0
                        ? <p className="text-muted" style={{ fontSize: 13 }}>No pending requests 🎉</p>
                        : <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {requests.slice(0, 5).map(r => (
                                <div key={r.id} className="flex justify-between items-center" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                                    <div>
                                        <div style={{ fontWeight: 500, fontSize: 13 }}>{r.title}</div>
                                        <div className="text-muted" style={{ fontSize: 11 }}>by {r.user_name || 'Unknown'} · {new Date(r.created_at).toLocaleDateString()}</div>
                                    </div>
                                    <span className="badge badge-warn">pending</span>
                                </div>
                            ))}
                        </div>
                    }
                </div>
            </div>
        </>
    );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  MAIN DASHBOARD ENTRY                                                      */
/* ═══════════════════════════════════════════════════════════════════════════ */
export default function Dashboard() {
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'manager';

    return (
        <div className="page">
            <div className="page-header">
                <h1>Welcome back, {user?.display_name} 👋</h1>
            </div>
            {isAdmin ? <AdminDashboard user={user} /> : <LearnerDashboard user={user} />}
        </div>
    );
}
