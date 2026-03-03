import { useState } from 'react';
import { resumeApi } from '../api/client';
import { Upload, FileText, CheckCircle } from 'lucide-react';

export default function Resume() {
    const [file, setFile] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');

    const upload = async (e) => {
        e.preventDefault();
        if (!file) return;
        setUploading(true); setError(''); setResult(null);
        const fd = new FormData();
        fd.append('file', file);
        try {
            const r = await resumeApi.upload(fd);
            setResult(r.data);
        } catch (err) {
            setError(err.response?.data?.detail || 'Upload failed');
        } finally { setUploading(false); }
    };

    return (
        <div className="page" style={{ maxWidth: 640 }}>
            <div className="page-header"><h1>Resume Parser</h1></div>
            <p className="text-muted" style={{ marginBottom: 20 }}>Upload your resume (PDF). AI will extract your skills and suggest relevant learning roadmaps.</p>

            <div className="card" style={{ marginBottom: 20 }}>
                <form onSubmit={upload}>
                    <div style={{ border: '2px dashed var(--border)', borderRadius: 8, padding: 32, textAlign: 'center', marginBottom: 16, background: 'var(--surface2)', transition: 'border-color .15s' }}
                        onDragOver={e => { e.preventDefault(); e.currentTarget.style.borderColor = 'var(--primary)'; }}
                        onDragLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; }}
                        onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f?.type === 'application/pdf') setFile(f); }}>
                        <Upload size={32} color="var(--muted)" style={{ marginBottom: 8 }} />
                        <p style={{ marginBottom: 8, fontSize: 14 }}>{file ? file.name : 'Drag & drop your PDF here'}</p>
                        <label className="btn btn-ghost btn-sm" style={{ cursor: 'pointer' }}>
                            Browse File
                            <input type="file" accept=".pdf" style={{ display: 'none' }} onChange={e => setFile(e.target.files[0])} />
                        </label>
                    </div>
                    {error && <div className="auth-error">{error}</div>}
                    <button className="btn btn-primary" disabled={!file || uploading} style={{ width: '100%' }}>
                        <Upload size={14} /> {uploading ? 'Processing…' : 'Upload & Analyze'}
                    </button>
                </form>
            </div>

            {result && (
                <div className="card">
                    <h3 style={{ marginBottom: 16, display: 'flex', gap: 6 }}><CheckCircle size={16} color="var(--success)" /> Analysis Complete</h3>

                    {result.extracted_skills?.length > 0 && (
                        <div style={{ marginBottom: 16 }}>
                            <div className="text-muted" style={{ fontSize: 12, marginBottom: 8 }}>Detected Skills</div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                {result.extracted_skills.map((s, i) => <span key={i} className="badge badge-primary">{s}</span>)}
                            </div>
                        </div>
                    )}

                    {result.experience_years != null && (
                        <div style={{ marginBottom: 16 }}>
                            <div className="text-muted" style={{ fontSize: 12, marginBottom: 4 }}>Experience</div>
                            <div>{result.experience_years} year{result.experience_years !== 1 ? 's' : ''}</div>
                        </div>
                    )}

                    {result.suggested_roadmap_titles?.length > 0 && (
                        <div>
                            <div className="text-muted" style={{ fontSize: 12, marginBottom: 8 }}>Suggested Roadmaps</div>
                            {result.suggested_roadmap_titles.map((t, i) => (
                                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
                                    <FileText size={13} color="var(--primary-h)" /> {t}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
