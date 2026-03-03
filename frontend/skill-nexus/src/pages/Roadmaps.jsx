import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { roadmapApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { Plus, Wand2, BookOpen, Lock, CheckCircle } from 'lucide-react';

function CreateModal({ onClose, onCreated }) {
    const [tab, setTab] = useState('manual'); // 'manual' | 'ai'
    const [form, setForm] = useState({ title: '', description: '' });
    const [prompt, setPrompt] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const createManual = async (e) => {
        e.preventDefault(); setLoading(true); setError('');
        try { const r = await roadmapApi.create(form); onCreated(r.data); }
        catch (err) { setError(err.response?.data?.detail || 'Error'); }
        finally { setLoading(false); }
    };

    const generateAI = async (e) => {
        e.preventDefault(); setLoading(true); setError('');
        try { const r = await roadmapApi.generate({ prompt }); onCreated(r.data); }
        catch (err) { setError(err.response?.data?.detail || 'Error'); }
        finally { setLoading(false); }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal" onClick={e => e.stopPropagation()}>
                <h2>New Roadmap</h2>
                <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
                    <button className={`btn btn-sm ${tab === 'manual' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab('manual')}>Manual</button>
                    <button className={`btn btn-sm ${tab === 'ai' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab('ai')}><Wand2 size={13} /> AI Generate</button>
                </div>
                {error && <div className="auth-error">{error}</div>}

                {tab === 'manual'
                    ? <form onSubmit={createManual}>
                        <div className="form-group"><label>Title</label><input className="input" required value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} /></div>
                        <div className="form-group"><label>Description</label><textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} /></div>
                        <div className="modal-footer"><button className="btn btn-ghost" type="button" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={loading}>{loading ? 'Creating…' : 'Create'}</button></div>
                    </form>
                    : <form onSubmit={generateAI}>
                        <div className="form-group">
                            <label>Describe the roadmap you want</label>
                            <textarea required placeholder='e.g. "Senior React Developer with testing and performance focus"' value={prompt} onChange={e => setPrompt(e.target.value)} style={{ minHeight: 100 }} />
                        </div>
                        <p className="text-muted" style={{ fontSize: 12, marginBottom: 16 }}>AI will generate a full node tree. This may take 10–20 seconds.</p>
                        <div className="modal-footer"><button className="btn btn-ghost" type="button" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={loading}>{loading ? 'Generating…' : 'Generate'}</button></div>
                    </form>
                }
            </div>
        </div>
    );
}

export default function Roadmaps() {
    const { user } = useAuth();
    const navigate = useNavigate();
    const [roadmaps, setRoadmaps] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const isAdmin = user?.role === 'admin';

    const load = () => {
        setLoading(true);
        roadmapApi.list({ published_only: !isAdmin, page_size: 50 })
            .then(r => setRoadmaps(r.data.items || []))
            .catch(() => { })
            .finally(() => setLoading(false));
    };

    useEffect(load, [isAdmin]);

    return (
        <div className="page">
            <div className="page-header">
                <h1>Roadmaps</h1>
                {isAdmin && <button className="btn btn-primary" onClick={() => setShowCreate(true)}><Plus size={15} /> New Roadmap</button>}
            </div>

            {loading ? <div className="loading-center"><div className="spinner" /></div>
                : roadmaps.length === 0
                    ? <div className="card" style={{ textAlign: 'center', padding: 40 }}>
                        <BookOpen size={32} color="var(--muted)" style={{ marginBottom: 8 }} />
                        <p className="text-muted">No roadmaps yet.{isAdmin && ' Create one above.'}</p>
                    </div>
                    : <div className="card-grid">
                        {roadmaps.map(rm => (
                            <div key={rm.id} className="card" style={{ cursor: 'pointer', transition: 'border-color .15s' }}
                                onClick={() => navigate(`/roadmaps/${rm.id}`)}
                                onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--primary)'}
                                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}>
                                <div className="flex justify-between items-center" style={{ marginBottom: 8 }}>
                                    <h3 style={{ fontSize: '1rem' }}>{rm.title}</h3>
                                    {rm.is_published
                                        ? <span className="badge badge-success"><CheckCircle size={11} /> Published</span>
                                        : <span className="badge badge-muted"><Lock size={11} /> Draft</span>}
                                </div>
                                {rm.description && <p className="text-muted" style={{ fontSize: 13, marginBottom: 10 }}>{rm.description}</p>}
                                <div className="text-muted" style={{ fontSize: 12 }}>{rm.node_count} nodes</div>
                            </div>
                        ))}
                    </div>
            }

            {showCreate && <CreateModal onClose={() => setShowCreate(false)} onCreated={(rm) => { setShowCreate(false); navigate(`/roadmaps/${rm.id}`); }} />}
        </div>
    );
}
