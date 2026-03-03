import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Register() {
    const { register } = useAuth();
    const navigate = useNavigate();
    const [form, setForm] = useState({ email: '', password: '', display_name: '' });
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const set = (k) => (e) => setForm(p => ({ ...p, [k]: e.target.value }));

    const submit = async (e) => {
        e.preventDefault();
        setError(''); setLoading(true);
        try {
            await register(form);
            navigate('/');
        } catch (err) {
            const detail = err.response?.data?.detail;
            setError(Array.isArray(detail) ? detail.map(d => d.msg).join(', ') : detail || 'Registration failed');
        } finally { setLoading(false); }
    };

    return (
        <div className="auth-wrap">
            <div className="auth-box">
                <h1>SkillNexus</h1>
                <p className="sub">Create your account</p>
                {error && <div className="auth-error">{error}</div>}
                <form onSubmit={submit}>
                    <div className="form-group">
                        <label>Display Name</label>
                        <input className="input" required autoFocus value={form.display_name} onChange={set('display_name')} />
                    </div>
                    <div className="form-group">
                        <label>Email</label>
                        <input className="input" type="email" required value={form.email} onChange={set('email')} />
                    </div>
                    <div className="form-group">
                        <label>Password <span style={{ color: 'var(--muted)' }}>( min 8 chars, 1 uppercase, 1 digit )</span></label>
                        <input className="input" type="password" required value={form.password} onChange={set('password')} />
                    </div>

                    <button className="btn btn-primary" style={{ width: '100%' }} disabled={loading}>
                        {loading ? 'Creating account…' : 'Create Account'}
                    </button>
                </form>
                <p style={{ textAlign: 'center', marginTop: 16, color: 'var(--muted)', fontSize: 13 }}>
                    Already have an account? <Link to="/login">Sign in</Link>
                </p>
            </div>
        </div>
    );
}
