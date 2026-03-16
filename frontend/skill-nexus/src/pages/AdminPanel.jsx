import { useEffect, useState } from 'react';
import { adminApi, userApi, roadmapApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { UserPlus, BarChart2, AlertTriangle, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

function AssignModal({ users, roadmaps, onClose, onAssigned }) {
    const [form, setForm] = useState({ user_ids: [], roadmap_id: '', strict_mode: false });
    const [saving, setSaving] = useState(false);

    const toggle = (id) => setForm(p => ({
        ...p,
        user_ids: p.user_ids.includes(id) ? p.user_ids.filter(x => x !== id) : [...p.user_ids, id],
    }));

    const submit = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            await adminApi.assign({ ...form });
            onAssigned();
        } catch (err) { alert(err.response?.data?.detail || 'Error'); }
        finally { setSaving(false); }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal" onClick={e => e.stopPropagation()}>
                <h2>Assign Roadmap</h2>
                <form onSubmit={submit}>
                    <div className="form-group">
                        <label>Roadmap</label>
                        <select required value={form.roadmap_id} onChange={e => setForm(p => ({ ...p, roadmap_id: e.target.value }))}>
                            <option value="">Select roadmap…</option>
                            {roadmaps.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}
                        </select>
                    </div>
                    <div className="form-group">
                        <label>Users (select one or more)</label>
                        <div style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 7, maxHeight: 180, overflowY: 'auto', padding: 8 }}>
                            {users.map(u => (
                                <label key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 4px', cursor: 'pointer', fontSize: 13 }}>
                                    <input type="checkbox" checked={form.user_ids.includes(u.id)} onChange={() => toggle(u.id)} />
                                    {u.display_name} <span className="text-muted">({u.email})</span>
                                </label>
                            ))}
                        </div>
                    </div>
                    <div className="form-group">
                        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                            <input type="checkbox" checked={form.strict_mode} onChange={e => setForm(p => ({ ...p, strict_mode: e.target.checked }))} />
                            Strict Mode (require quiz before marking done)
                        </label>
                    </div>
                    <div className="modal-footer">
                        <button className="btn btn-ghost" type="button" onClick={onClose}>Cancel</button>
                        <button className="btn btn-primary" disabled={saving || !form.roadmap_id || form.user_ids.length === 0}>{saving ? 'Assigning…' : 'Assign'}</button>
                    </div>
                </form>
            </div>
        </div>
    );
}

export default function AdminPanel() {
    const { user } = useAuth();
    const navigate = useNavigate();
    const [tab, setTab] = useState('assignments');
    const [dashboard, setDashboard] = useState(null);
    const [assignments, setAssignments] = useState([]);
    const [skillGaps, setSkillGaps] = useState([]);
    const [requests, setRequests] = useState([]);
    const [users, setUsers] = useState([]);
    const [roadmaps, setRoadmaps] = useState([]);
    const [showAssign, setShowAssign] = useState(false);
    const [loading, setLoading] = useState(true);
    const [generatingReq, setGeneratingReq] = useState(null);

    const isManager = user?.role === 'manager';
    const userNameById = Object.fromEntries(users.map(u => [u.id, u.display_name]));
    const roadmapTitleById = Object.fromEntries(roadmaps.map(r => [r.id, r.title]));

    const load = async () => {
        setLoading(true);
        try {
            const [dash, asgn, reqs] = await Promise.all([
                adminApi.dashboard(),
                adminApi.getAssignments({ page_size: 50 }),
                adminApi.getRoadmapRequests(),
            ]);
            setDashboard(dash.data);
            setAssignments(asgn.data.items || []);
            setRequests(reqs.data || []);

            if (!isManager) {
                const [uList, rList] = await Promise.all([
                    userApi.list({ page_size: 100 }),
                    roadmapApi.list({ published_only: false, page_size: 100 }),
                ]);
                const usersData = uList.data.items || uList.data.users || [];
                const roadmapsData = rList.data.items || [];
                setUsers(usersData);
                setRoadmaps(roadmapsData);

                // skill-gaps endpoint requires roadmap_id; load safely using first roadmap if present
                if (roadmapsData.length > 0) {
                    try {
                        const gaps = await adminApi.skillGaps({ roadmap_id: roadmapsData[0].id });
                        setSkillGaps(gaps.data || []);
                    } catch {
                        setSkillGaps([]);
                    }
                } else {
                    setSkillGaps([]);
                }
            }
        } catch { /* noop */ }
        finally { setLoading(false); }
    };

    const handleGenerateRequest = async (req) => {
        if (!window.confirm(`Generate an AI Roadmap for "${req.title}"?`)) return;
        setGeneratingReq(req.id);
        try {
            const r = await roadmapApi.generate({ prompt: `Create a comprehensive roadmap for ${req.title}` });
            await adminApi.updateRoadmapRequest(req.id, { status: 'fulfilled' });
            setRequests(p => p.filter(x => x.id !== req.id));
            navigate(`/roadmaps/${r.data.id}`);
        } catch (err) {
            alert(err.response?.data?.detail || 'Error generating roadmap via AI');
            setGeneratingReq(null);
        }
    };


    useEffect(() => { load(); }, []);

    const removeAssignment = async (id) => {
        if (!window.confirm('Remove assignment?')) return;
        try { await adminApi.deleteAssignment(id); setAssignments(a => a.filter(x => x.id !== id)); }
        catch (err) { alert(err.response?.data?.detail || 'Error'); }
    };

    const stats = dashboard?.stats;

    return (
        <div className="page">
            <div className="page-header">
                <h1>{isManager ? 'Team Overview' : 'L&D Admin'}</h1>
                {!isManager && <button className="btn btn-primary" onClick={() => setShowAssign(true)}><UserPlus size={14} /> Assign</button>}
            </div>

            {loading ? <div className="loading-center"><div className="spinner" /></div> : (
                <>
                    {/* Stats */}
                    {stats && (
                        <div className="stats-row" style={{ marginBottom: 24 }}>
                            <div className="stat-card"><div className="value">{stats.total_users}</div><div className="label">Total Users</div></div>
                            <div className="stat-card"><div className="value">{stats.total_roadmaps}</div><div className="label">Roadmaps</div></div>
                            <div className="stat-card"><div className="value">{stats.total_assignments}</div><div className="label">Assignments</div></div>
                            <div className="stat-card"><div className="value" style={{ color: 'var(--success)' }}>{stats.avg_completion_percentage?.toFixed(0)}%</div><div className="label">Avg Completion</div></div>
                        </div>
                    )}

                    {/* Tabs */}
                    <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
                        {['assignments', 'requests'].map(t => (
                            <button key={t} className={`btn btn-sm ${tab === t ? 'btn-primary' : 'btn-ghost'}`} style={{ textTransform: 'capitalize' }} onClick={() => setTab(t)}>
                                {t === 'assignments' ? <><Users size={13} /> Assignments</> : <><Users size={13} /> Requests</>}
                            </button>
                        ))}
                    </div>

                    {/* Assignments table */}
                    {tab === 'assignments' && (
                        <div className="table-wrap">
                            <table>
                                <thead>
                                    <tr><th>User</th><th>Roadmap</th><th>Status</th><th>Progress</th><th>Last Active</th>{!isManager && <th>Actions</th>}</tr>
                                </thead>
                                <tbody>
                                    {assignments.length === 0
                                        ? <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--muted)' }}>No assignments yet.</td></tr>
                                        : assignments.map(a => (
                                            <tr key={a.id}>
                                                <td>{a.user_display_name || userNameById[a.user_id] || a.user_id}</td>
                                                <td>{a.roadmap_title || roadmapTitleById[a.roadmap_id] || a.roadmap_id}</td>
                                                <td><span className={`badge badge-${a.status === 'active' ? 'primary' : a.status === 'completed' ? 'success' : 'muted'}`}>{a.status}</span>
                                                    {a.strict_mode && <span className="badge badge-warn" style={{ marginLeft: 4 }}>strict</span>}
                                                </td>
                                                <td>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                        <div className="progress-bar" style={{ width: 80 }}>
                                                            <div className="progress-bar-fill" style={{ width: `${a.completion_percentage || 0}%` }} />
                                                        </div>
                                                        <span style={{ fontSize: 12 }}>{(a.completion_percentage || 0).toFixed(0)}%</span>
                                                    </div>
                                                </td>
                                                <td className="text-muted" style={{ fontSize: 12 }}>{a.last_active_at ? new Date(a.last_active_at).toLocaleDateString() : '—'}</td>
                                                {!isManager && (
                                                    <td><button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)' }} onClick={() => removeAssignment(a.id)}>Remove</button></td>
                                                )}
                                            </tr>
                                        ))
                                    }
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Roadmap Requests */}
                    {tab === 'requests' && (
                        <div className="table-wrap">
                            <table>
                                <thead>
                                    <tr><th>User ID / Name</th><th>Email</th><th>Requested Roadmap</th><th>Date</th>{!isManager && <th>Actions</th>}</tr>
                                </thead>
                                <tbody>
                                    {requests.length === 0
                                        ? <tr><td colSpan={!isManager ? 5 : 4} style={{ textAlign: 'center', color: 'var(--muted)' }}>No requests yet.</td></tr>
                                        : requests.map(r => (
                                            <tr key={r.id}>
                                                <td>{r.user_name || r.user_id}</td>
                                                <td>{r.user_email || '—'}</td>
                                                <td><span style={{ fontWeight: 500 }}>{r.title}</span></td>
                                                <td className="text-muted" style={{ fontSize: 12 }}>{new Date(r.created_at).toLocaleDateString()}</td>
                                                {!isManager && (
                                                    <td style={{ textAlign: 'right' }}>
                                                        <button 
                                                            className="btn btn-sm btn-primary" 
                                                            disabled={generatingReq === r.id}
                                                            onClick={() => handleGenerateRequest(r)}
                                                        >
                                                            {generatingReq === r.id ? 'Generating...' : 'AI Generate'}
                                                        </button>
                                                    </td>
                                                )}
                                            </tr>
                                        ))
                                    }
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            )}

            {showAssign && (
                <AssignModal
                    users={users} roadmaps={roadmaps}
                    onClose={() => setShowAssign(false)}
                    onAssigned={() => { setShowAssign(false); load(); }}
                />
            )}
        </div>
    );
}
