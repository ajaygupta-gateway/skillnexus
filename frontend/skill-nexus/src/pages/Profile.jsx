import { useEffect, useState } from 'react';
import { userApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { User, Save } from 'lucide-react';

export default function Profile() {
    const { user, reload } = useAuth();
    const [form, setForm] = useState({ display_name: '', current_role_title: '' });
    const [saving, setSaving] = useState(false);
    const [success, setSuccess] = useState(false);

    useEffect(() => {
        if (user) setForm({ display_name: user.display_name || '', current_role_title: user.current_role_title || '' });
    }, [user]);

    const save = async (e) => {
        e.preventDefault(); setSaving(true); setSuccess(false);
        try { await userApi.update(form); await reload(); setSuccess(true); setTimeout(() => setSuccess(false), 2000); }
        catch (err) { alert(err.response?.data?.detail || 'Error'); }
        finally { setSaving(false); }
    };

    if (!user) return null;
    const xpPct = (user.xp_balance % 500) / 5;

    return (
        <div className="page" style={{ maxWidth: 600 }}>
            <div className="page-header"><h1>Profile</h1></div>

            <div className="card" style={{ marginBottom: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
                    <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.5rem', fontWeight: 700, color: '#fff' }}>
                        {user.display_name?.[0]?.toUpperCase()}
                    </div>
                    <div>
                        <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>{user.display_name}</div>
                        <div className="text-muted" style={{ fontSize: 13 }}>{user.email} · <span className="badge badge-primary">{user.role}</span></div>
                    </div>
                </div>

                {/* XP bar */}
                <div style={{ marginBottom: 16 }}>
                    <div className="flex justify-between" style={{ marginBottom: 6, fontSize: 13 }}>
                        <span>Level {user.level}</span>
                        <span className="text-muted">{user.xp_balance} XP total</span>
                    </div>
                    <div className="progress-bar">
                        <div className="progress-bar-fill" style={{ width: `${xpPct}%` }} />
                    </div>
                    <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>{500 - (user.xp_balance % 500)} XP to Level {user.level + 1}</div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                    {[['🔥 Streak', `${user.streak_count} days`], ['⚡ XP', user.xp_balance], ['🏆 Level', user.level]].map(([l, v]) => (
                        <div key={l} style={{ background: 'var(--surface2)', borderRadius: 8, padding: '10px 14px', textAlign: 'center' }}>
                            <div style={{ fontWeight: 700, fontSize: '1.2rem' }}>{v}</div>
                            <div className="text-muted" style={{ fontSize: 12 }}>{l}</div>
                        </div>
                    ))}
                </div>
            </div>

            <div className="card">
                <h3 style={{ marginBottom: 16 }}><User size={15} style={{ marginRight: 6, verticalAlign: 'middle' }} />Edit Profile</h3>
                <form onSubmit={save}>
                    <div className="form-group"><label>Display Name</label><input className="input" value={form.display_name} onChange={e => setForm(p => ({ ...p, display_name: e.target.value }))} /></div>
                    <div className="form-group"><label>Current Role Title</label><input className="input" placeholder="e.g. Frontend Developer" value={form.current_role_title} onChange={e => setForm(p => ({ ...p, current_role_title: e.target.value }))} /></div>
                    <button className="btn btn-primary" disabled={saving}>
                        <Save size={14} /> {saving ? 'Saving…' : success ? 'Saved ✓' : 'Save Changes'}
                    </button>
                </form>
            </div>
        </div>
    );
}
