import { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { userApi } from '../api/client';
import { Trophy, Zap, Flame, BarChart2 } from 'lucide-react';

export default function Dashboard() {
    const { user } = useAuth();
    const [leaderboard, setLeaderboard] = useState([]);
    const [txns, setTxns] = useState([]);

    useEffect(() => {
        userApi.leaderboard().then(r => setLeaderboard(r.data.entries || [])).catch(() => { });
        userApi.transactions().then(r => setTxns(r.data.slice(0, 10))).catch(() => { });
    }, []);

    const xpToNext = 500 - (user?.xp_balance % 500);
    const pct = Math.round(((user?.xp_balance % 500) / 500) * 100);

    return (
        <div className="page">
            <div className="page-header">
                <h1>Welcome back, {user?.display_name} 👋</h1>
            </div>

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
        </div>
    );
}
