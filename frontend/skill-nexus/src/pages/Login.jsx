import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Login() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const [form, setForm] = useState({ email: '', password: '' });
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        setError(''); setLoading(true);
        try {
            await login(form.email, form.password);
            navigate('/');
        } catch (err) {
            setError(err.response?.data?.detail || 'Invalid credentials');
        } finally { setLoading(false); }
    };

    return (
        <div className="auth-wrap">
            <div className="auth-box">
                <h1>SkillNexus</h1>
                <p className="sub">Sign in to your account</p>
                {error && <div className="auth-error">{error}</div>}
                <form onSubmit={submit}>
                    <div className="form-group">
                        <label>Email</label>
                        <input className="input" type="email" required autoFocus
                            value={form.email} onChange={e => setForm(p => ({ ...p, email: e.target.value }))} />
                    </div>
                    <div className="form-group">
                        <label>Password</label>
                        <input className="input" type="password" required
                            value={form.password} onChange={e => setForm(p => ({ ...p, password: e.target.value }))} />
                    </div>
                    <button className="btn btn-primary" style={{ width: '100%' }} disabled={loading}>
                        {loading ? 'Signing in…' : 'Sign In'}
                    </button>
                </form>
                <p style={{ textAlign: 'center', marginTop: 16, color: 'var(--muted)', fontSize: 13 }}>
                    No account? <Link to="/register">Register</Link>
                </p>
            </div>
        </div>
    );
}
