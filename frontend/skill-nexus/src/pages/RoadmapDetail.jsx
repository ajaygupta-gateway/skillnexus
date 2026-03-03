import { useEffect, useState, useCallback, useRef } from 'react';
import dagre from 'dagre';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useParams, useNavigate } from 'react-router-dom';
import {
    ReactFlow, Background, Controls, MiniMap,
    useNodesState, useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { roadmapApi, progressApi, chatApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { Send, CheckCircle, Clock, Lock, Plus, Trash2, BookOpen, MessageSquare, X, Settings } from 'lucide-react';

/* ─── Flatten nested tree from API into a flat array ────────────────── */
// The API returns nodes as a nested tree (children inside parents).
// We need a flat array to build the graph and compute order.
function flattenTree(nodeList) {
    const result = [];
    function walk(nodes) {
        for (const node of nodes) {
            const { children, ...rest } = node;
            result.push(rest);
            if (children && children.length > 0) walk(children);
        }
    }
    walk(nodeList);
    return result;
}

/* ─── Compute which nodes are "unlocked" given the ordered sequence ─── */
// Rule: first node is always in_progress for enrolled users.
// Node N is unlocked when node N-1 is done AND quiz_passed = true.
function computeEffectiveStatus(node, orderedNodes, progressMap, quizPassedMap, isAssigned) {
    const nodeStatus = progressMap[node.id];
    if (nodeStatus === 'done') return 'done';
    if (nodeStatus === 'in_progress') return 'in_progress';

    const idx = orderedNodes.findIndex(n => n.id === node.id);

    // First node: always unlocked for enrolled users
    if (idx === 0) return isAssigned ? 'in_progress' : 'locked';
    if (idx < 0) return 'locked';

    // Subsequent nodes: check predecessor is done AND quiz passed
    const prev = orderedNodes[idx - 1];
    if (progressMap[prev.id] === 'done' && quizPassedMap[prev.id]) {
        return 'in_progress'; // unlocked
    }
    return 'locked';
}

/* ─── Build React-Flow nodes + edges from flat API response ─────────── */
function buildGraph(nodes, progressMap, quizPassedMap, isAssigned, selectedId, onClickNode) {
    const W = 220, H = 80;

    // Sort nodes for the linear sequence (by order_index)
    const orderedNodes = [...nodes].sort((a, b) => (a.order_index || 0) - (b.order_index || 0));

    // 1. Setup Dagre graph
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: 'TB', nodesep: 50, ranksep: 80 });
    g.setDefaultEdgeLabel(() => ({}));

    nodes.forEach(n => { g.setNode(n.id, { width: W, height: H }); });

    // Build edges from parent_id relationships
    const xyEdges = nodes
        .filter(n => n.parent_id)
        .map(n => {
            g.setEdge(n.parent_id, n.id);
            return {
                id: `e-${n.parent_id}-${n.id}`,
                source: n.parent_id,
                target: n.id,
                style: { stroke: 'var(--border)', strokeWidth: 2 },
                animated: progressMap[n.id] === 'in_progress',
            };
        });

    // Link root nodes sequentially by order_index for a vertical spine
    const roots = nodes
        .filter(n => !n.parent_id)
        .sort((a, b) => (a.order_index || 0) - (b.order_index || 0));
    if (roots.length > 1) {
        for (let i = 0; i < roots.length - 1; i++) {
            g.setEdge(roots[i].id, roots[i + 1].id);
            xyEdges.push({
                id: `e-root-${roots[i].id}-${roots[i + 1].id}`,
                source: roots[i].id,
                target: roots[i + 1].id,
                style: { stroke: 'var(--border)', strokeWidth: 3, strokeDasharray: '5,5' },
                animated: false,
            });
        }
    }

    dagre.layout(g);

    const xyNodes = nodes.map((n) => {
        const dNode = g.node(n.id);
        const effectiveStatus = computeEffectiveStatus(n, orderedNodes, progressMap, quizPassedMap, isAssigned);
        return {
            id: n.id,
            type: 'roadmapNode',
            position: {
                x: n.position_x !== 0 ? n.position_x : dNode.x - W / 2,
                y: n.position_y !== 0 ? n.position_y : dNode.y - H / 2,
            },
            data: {
                label: `${typeof n.order_index !== 'undefined' ? n.order_index + 1 + '.' : ''} ${n.title}`,
                status: effectiveStatus,
                selected: n.id === selectedId,
                onClick: () => onClickNode(n),
            },
            draggable: true,
        };
    });

    return { xyNodes, xyEdges };
}

/* ─── Quiz Modal ─────────────────────────────────────────────────────── */
function QuizModal({ node, onClose, onPassed }) {
    const [quiz, setQuiz] = useState(null);
    // quizSel: { [question_number_string]: optionKey }  e.g. { "1": "A", "2": "C", "3": "B" }
    const [quizSel, setQuizSel] = useState({});
    const [quizResult, setQuizResult] = useState(null);
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        setLoading(true);
        chatApi.generateQuiz(node.id, node.roadmap_id)
            .then(r => setQuiz(r.data))
            .catch(() => alert('Could not generate quiz. Please try again.'))
            .finally(() => setLoading(false));
    }, [node.id, node.roadmap_id]);

    const allAnswered = quiz && Object.keys(quizSel).length >= quiz.questions.length;

    const submit = async () => {
        setSubmitting(true);
        try {
            // Build dict: { "1": "A", "2": "C", "3": "B" } — what backend expects
            const answers = {};
            quiz.questions.forEach(q => {
                answers[String(q.question_number)] = quizSel[String(q.question_number)] || '';
            });
            const r = await chatApi.submitQuiz(node.id, node.roadmap_id, { answers });
            setQuizResult(r.data);
            if (r.data.passed) {
                setTimeout(() => onPassed(), 1800);
            }
        } catch (err) {
            const detail = err.response?.data?.detail || 'Submit failed. Please try again.';
            alert(detail);
        }
        finally { setSubmitting(false); }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                    <h2 style={{ margin: 0 }}>🧠 Node Quiz: {node.title}</h2>
                    <button className="btn btn-ghost btn-sm" onClick={onClose}><X size={14} /></button>
                </div>
                <p className="text-muted" style={{ fontSize: 13, marginBottom: 16 }}>
                    Answer all questions correctly to unlock the next node.
                </p>

                {loading && <div className="loading-center"><div className="spinner" /></div>}

                {quiz && !quizResult && (
                    <>
                        {quiz.questions.map((q) => {
                            const qKey = String(q.question_number);
                            return (
                                <div key={qKey} style={{ marginBottom: 18 }}>
                                    <p style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
                                        Q{q.question_number}. {q.question}
                                    </p>
                                    {q.options.map((opt) => (
                                        <div key={opt.key}
                                            className={`quiz-option ${quizSel[qKey] === opt.key ? 'selected' : ''}`}
                                            onClick={() => setQuizSel(s => ({ ...s, [qKey]: opt.key }))}>
                                            <strong style={{ marginRight: 8 }}>{opt.key}.</strong>{opt.text}
                                        </div>
                                    ))}
                                </div>
                            );
                        })}
                        <div className="modal-footer">
                            <button className="btn btn-ghost" onClick={onClose}>Skip for now</button>
                            <button className="btn btn-primary"
                                disabled={submitting || !allAnswered}
                                onClick={submit}>
                                {submitting ? 'Submitting…' : 'Submit Quiz'}
                            </button>
                        </div>
                    </>
                )}

                {quizResult && (
                    <div style={{
                        background: quizResult.passed ? 'rgba(34,197,94,.12)' : 'rgba(239,68,68,.12)',
                        border: `1px solid ${quizResult.passed ? 'var(--success)' : 'var(--danger)'}`,
                        borderRadius: 12, padding: 20, textAlign: 'center'
                    }}>
                        <p style={{ fontSize: 28, marginBottom: 8 }}>{quizResult.passed ? '🎉' : '😕'}</p>
                        <p style={{ fontWeight: 700, fontSize: 16 }}>
                            {quizResult.passed ? 'Passed!' : 'Not quite!'} — {quizResult.score}/{quizResult.total}
                        </p>
                        {quizResult.passed
                            ? <p className="text-muted" style={{ marginTop: 6 }}>Next node is now unlocked!</p>
                            : <div className="modal-footer" style={{ justifyContent: 'center' }}>
                                <button className="btn btn-primary" onClick={() => { setQuizResult(null); setQuizSel({}); }}>Try Again</button>
                            </div>
                        }
                    </div>
                )}
            </div>
        </div>
    );
}

/* ─── Markdown renderer for AI messages ───────────────────────────── */
const mdComponents = {
    p: ({ children }) => <p style={{ margin: '0 0 8px 0', lineHeight: 1.6 }}>{children}</p>,
    h1: ({ children }) => <p style={{ fontWeight: 700, fontSize: 15, margin: '10px 0 4px' }}>{children}</p>,
    h2: ({ children }) => <p style={{ fontWeight: 700, fontSize: 14, margin: '10px 0 4px' }}>{children}</p>,
    h3: ({ children }) => <p style={{ fontWeight: 600, fontSize: 13, margin: '8px 0 4px' }}>{children}</p>,
    ul: ({ children }) => <ul style={{ margin: '4px 0 8px 0', paddingLeft: 18 }}>{children}</ul>,
    ol: ({ children }) => <ol style={{ margin: '4px 0 8px 0', paddingLeft: 18 }}>{children}</ol>,
    li: ({ children }) => <li style={{ marginBottom: 3, lineHeight: 1.5 }}>{children}</li>,
    code: ({ inline, children }) => inline
        ? <code style={{ background: 'rgba(255,255,255,0.12)', borderRadius: 4, padding: '1px 5px', fontSize: 12, fontFamily: 'monospace' }}>{children}</code>
        : <pre style={{ background: 'rgba(0,0,0,0.35)', borderRadius: 8, padding: '10px 12px', overflowX: 'auto', margin: '6px 0' }}>
            <code style={{ fontSize: 12, fontFamily: 'monospace', whiteSpace: 'pre' }}>{children}</code>
        </pre>,
    a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer" style={{ color: 'var(--primary-h)', textDecoration: 'underline' }}>{children}</a>,
    strong: ({ children }) => <strong style={{ fontWeight: 700 }}>{children}</strong>,
    em: ({ children }) => <em style={{ fontStyle: 'italic' }}>{children}</em>,
    hr: () => <hr style={{ border: 'none', borderTop: '1px solid rgba(255,255,255,0.1)', margin: '8px 0' }} />,
};

/* ─── Chat Panel ─────────────────────────────────────────────────────── */
function ChatPanel({ node }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [sending, setSending] = useState(false);
    const bottomRef = useRef();

    useEffect(() => {
        if (!node) return;
        setMessages([]);
        chatApi.getMessages(node.id, node.roadmap_id)
            .then(r => setMessages(r.data.messages || []))
            .catch(() => { });
    }, [node?.id, node?.roadmap_id]);

    useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, sending]);

    const send = async () => {
        if (!input.trim() || sending) return;
        const text = input.trim(); setInput(''); setSending(true);
        setMessages(m => [...m, { role: 'user', content: text }]);
        try {
            const r = await chatApi.sendMessage(node.id, node.roadmap_id, { content: text });
            setMessages(m => [...m, { role: 'assistant', content: r.data.content }]);
        } catch { setMessages(m => [...m, { role: 'assistant', content: '⚠️ Could not get a response.' }]); }
        finally { setSending(false); }
    };

    return (
        <div className="chat-panel">
            <div className="chat-messages">
                {messages.length === 0 && (
                    <p className="text-muted" style={{ textAlign: 'center', marginTop: 20, fontSize: 13 }}>
                        Ask me anything about <strong>{node?.title}</strong>
                    </p>
                )}
                {messages.map((m, i) => (
                    <div key={i} className={`chat-bubble ${m.role}`}>
                        {m.role === 'assistant'
                            ? <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                                {m.content}
                            </ReactMarkdown>
                            : m.content
                        }
                    </div>
                ))}
                {sending && (
                    <div className="chat-bubble assistant" style={{ display: 'flex', gap: 4, alignItems: 'center', padding: '10px 14px' }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--muted)', animation: 'pulse 1s infinite 0s' }} />
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--muted)', animation: 'pulse 1s infinite 0.2s' }} />
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--muted)', animation: 'pulse 1s infinite 0.4s' }} />
                    </div>
                )}
                <div ref={bottomRef} />
            </div>
            <div className="chat-input-row">
                <input className="input" placeholder="Ask a question…"
                    value={input} onChange={e => setInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && send()} />
                <button className="btn btn-primary btn-sm" onClick={send} disabled={sending || !input.trim()}>
                    <Send size={14} />
                </button>
            </div>
        </div>
    );
}

/* ─── Node Info Panel ────────────────────────────────────────────────── */
function NodeInfoPanel({ node, effectiveStatus, onMarkDone, onMarkInProgress, isAdmin, onDelete, isAssigned }) {
    const [saving, setSaving] = useState(false);
    const isLocked = effectiveStatus === 'locked';
    const isDone = effectiveStatus === 'done';

    return (
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
                <h3 style={{ marginBottom: 4 }}>{node.title}</h3>
                {node.description && <p className="text-muted" style={{ fontSize: 13 }}>{node.description}</p>}
            </div>

            {/* Status section */}
            {(isAssigned || isAdmin) ? (
                <div>
                    <div className="text-muted" style={{ fontSize: 12, marginBottom: 8 }}>Your Status</div>
                    {isLocked ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'var(--surface2)', borderRadius: 8, border: '1px solid var(--border)' }}>
                            <Lock size={14} color="var(--muted)" />
                            <span style={{ fontSize: 13, color: 'var(--muted)' }}>
                                Complete the previous node and pass its quiz to unlock this one.
                            </span>
                        </div>
                    ) : isDone ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--success)', fontSize: 13, padding: '8px 0' }}>
                            <CheckCircle size={16} /> <strong>Completed!</strong>
                        </div>
                    ) : (
                        /* Unlocked node — show both buttons */
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                            <button className="btn btn-ghost btn-sm" disabled={saving}
                                onClick={async () => { setSaving(true); await onMarkInProgress(node); setSaving(false); }}>
                                <Clock size={13} /> In Progress
                            </button>
                            <button className="btn btn-primary btn-sm" disabled={saving}
                                onClick={() => onMarkDone(node)}>
                                <CheckCircle size={13} /> Mark as Done
                            </button>
                        </div>
                    )}
                </div>
            ) : (
                <div style={{ padding: 12, background: 'var(--surface2)', borderRadius: 8, borderLeft: '3px solid var(--primary)' }}>
                    <p style={{ fontSize: 13, color: 'var(--primary)', margin: 0 }}>
                        📌 Enroll in this roadmap to track your progress and unlock nodes.
                    </p>
                </div>
            )}

            {/* Resources */}
            {node.resources?.length > 0 && (
                <div>
                    <div className="text-muted" style={{ fontSize: 12, marginBottom: 6 }}>Resources</div>
                    {node.resources.map((r, i) => (
                        <a key={i} href={r.url} target="_blank" rel="noreferrer"
                            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 0', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
                            <BookOpen size={13} color="var(--primary-h)" /> {r.title}
                            <span className="badge badge-muted" style={{ marginLeft: 'auto' }}>{r.type || 'link'}</span>
                        </a>
                    ))}
                </div>
            )}

            {isAdmin && (
                <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)', borderColor: 'var(--danger)', marginTop: 4 }}
                    onClick={() => onDelete(node)}>
                    <Trash2 size={13} /> Delete Node
                </button>
            )}
        </div>
    );
}

/* ─── Add Node Modal ─────────────────────────────────────────────────── */
function AddNodeModal({ roadmapId, nodes, onClose, onAdded }) {
    const [form, setForm] = useState({ title: '', description: '', parent_id: '' });
    const [saving, setSaving] = useState(false);

    const submit = async (e) => {
        e.preventDefault(); setSaving(true);
        try {
            const payload = { ...form, parent_id: form.parent_id || null };
            const r = await roadmapApi.addNode(roadmapId, payload);
            onAdded(r.data);
        } catch (err) { alert(err.response?.data?.detail || 'Error'); }
        finally { setSaving(false); }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal" onClick={e => e.stopPropagation()}>
                <h2>Add Node</h2>
                <form onSubmit={submit}>
                    <div className="form-group"><label>Title</label><input className="input" required autoFocus value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} /></div>
                    <div className="form-group"><label>Description</label><textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} /></div>
                    <div className="form-group">
                        <label>Parent Node (optional)</label>
                        <select value={form.parent_id} onChange={e => setForm(p => ({ ...p, parent_id: e.target.value }))}>
                            <option value="">— Root (no parent) —</option>
                            {nodes.map(n => <option key={n.id} value={n.id}>{n.title}</option>)}
                        </select>
                    </div>
                    <div className="modal-footer">
                        <button className="btn btn-ghost" type="button" onClick={onClose}>Cancel</button>
                        <button className="btn btn-primary" disabled={saving}>{saving ? 'Adding…' : 'Add Node'}</button>
                    </div>
                </form>
            </div>
        </div>
    );
}

/* ─── Custom node component ─────────────────────────────────────────── */
function RoadmapNode({ data }) {
    const icons = {
        done: <CheckCircle size={12} color="var(--success)" />,
        in_progress: <Clock size={12} color="var(--warn)" />,
        locked: <Lock size={12} color="var(--muted)" />,
    };
    const labels = { done: 'Done', in_progress: 'In Progress', locked: 'Locked' };
    const s = data.status || 'locked';
    return (
        <div className={`sn-node ${data.selected ? 'selected' : ''} status-${s}`} onClick={data.onClick}>
            <div className="node-title">{data.label}</div>
            <div className="node-status">{icons[s]} {labels[s]}</div>
        </div>
    );
}
const nodeTypes = { roadmapNode: RoadmapNode };

/* ─── Main RoadmapDetail page ────────────────────────────────────────── */
export default function RoadmapDetail() {
    const { id } = useParams();
    const { user, reload: reloadUser } = useAuth();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin';

    const [roadmap, setRoadmap] = useState(null);
    const [flatNodes, setFlatNodes] = useState([]);
    const [progressMap, setProgressMap] = useState({});
    const [quizPassedMap, setQuizPassedMap] = useState({});
    const [isAssigned, setIsAssigned] = useState(false);
    const [enrolling, setEnrolling] = useState(false);
    const [selectedNode, setSelectedNode] = useState(null);
    const [sideTab, setSideTab] = useState('info');
    const [showAddNode, setShowAddNode] = useState(false);
    const [quizNode, setQuizNode] = useState(null);
    const [loading, setLoading] = useState(true);
    const [xpToast, setXpToast] = useState(null); // { amount: 25, nodeName: '...' }

    const [xyNodes, setXyNodes, onXyNodesChange] = useNodesState([]);
    const [xyEdges, setXyEdges, onXyEdgesChange] = useEdgesState([]);

    const handleNodeClick = useCallback((n) => {
        setSelectedNode(n); setSideTab('info');
    }, []);

    const rebuildGraph = useCallback((nodes, pMap, qMap, selId, assigned) => {
        const { xyNodes: nn, xyEdges: ee } = buildGraph(nodes, pMap, qMap, assigned ?? isAssigned, selId, handleNodeClick);
        setXyNodes(nn); setXyEdges(ee);
    }, [handleNodeClick, isAssigned]);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const r = await roadmapApi.get(id);
            setRoadmap(r.data);
            // API returns a NESTED tree — flatten it to get ALL nodes
            const nodes = flattenTree(r.data.nodes || []);
            setFlatNodes(nodes);

            let pMap = {};
            let qMap = {};
            let assigned = false;

            try {
                const pr = await progressApi.getRoadmapProgress(id);
                const statuses = pr.data.node_statuses || [];
                statuses.forEach(p => {
                    pMap[p.node_id] = p.status;
                    qMap[p.node_id] = p.quiz_passed || false;
                });
                // If we got a successful response, the user IS assigned
                assigned = true;
            } catch (err) {
                // 403/404 means not assigned
                assigned = false;
            }

            setIsAssigned(assigned);
            setProgressMap(pMap);
            setQuizPassedMap(qMap);
            rebuildGraph(nodes, pMap, qMap, null, assigned);
        } catch { navigate('/roadmaps'); }
        finally { setLoading(false); }
    }, [id, navigate, rebuildGraph]);

    useEffect(() => { load(); }, [load]);

    const handleEnroll = async () => {
        setEnrolling(true);
        try {
            await roadmapApi.enroll(id);
            await load(); // reload to pick up new assignment and first node in_progress
        } catch (err) {
            alert(err.response?.data?.detail || 'Could not enroll. Please try again.');
        } finally {
            setEnrolling(false);
        }
    };

    // Called when learner clicks "Mark as Done" — show quiz FIRST
    // Backend is only updated after the quiz is passed (in handleQuizPassed)
    const handleMarkDone = (node) => {
        setQuizNode(node); // opens quiz modal
    };

    // Called when learner starts a node
    const handleMarkInProgress = async (node) => {
        try {
            await progressApi.updateNode(node.roadmap_id, node.id, { status: 'in_progress' });
            const newPMap = { ...progressMap, [node.id]: 'in_progress' };
            setProgressMap(newPMap);
            rebuildGraph(flatNodes, newPMap, quizPassedMap, selectedNode?.id);
        } catch (err) {
            alert(err.response?.data?.detail || 'Could not update status');
        }
    };

    // Called when quiz is passed — NOW mark node as done and unlock the next node
    const handleQuizPassed = async () => {
        if (!quizNode) return;

        // 1. Mark the completed node as 'done' in the backend
        try {
            await progressApi.updateNode(quizNode.roadmap_id, quizNode.id, { status: 'done' });
        } catch {
            // If already done, fine
        }

        // 2. Update local state: node is done + quiz passed
        const newPMap = { ...progressMap, [quizNode.id]: 'done' };
        const newQMap = { ...quizPassedMap, [quizNode.id]: true };
        setProgressMap(newPMap);
        setQuizPassedMap(newQMap);

        // 3. Unlock the next node in the ordered sequence
        const orderedNodes = [...flatNodes].sort((a, b) => (a.order_index || 0) - (b.order_index || 0));
        const currentIdx = orderedNodes.findIndex(n => n.id === quizNode.id);
        if (currentIdx >= 0 && currentIdx + 1 < orderedNodes.length) {
            const nextNode = orderedNodes[currentIdx + 1];
            try {
                await progressApi.updateNode(quizNode.roadmap_id, nextNode.id, { status: 'in_progress' });
                const withNext = { ...newPMap, [nextNode.id]: 'in_progress' };
                setProgressMap(withNext);
                rebuildGraph(flatNodes, withNext, newQMap, selectedNode?.id);
            } catch {
                rebuildGraph(flatNodes, newPMap, newQMap, selectedNode?.id);
            }
        } else {
            rebuildGraph(flatNodes, newPMap, newQMap, selectedNode?.id);
        }

        // 4. Show XP toast + refresh sidebar user data
        setXpToast({ amount: 25, nodeName: quizNode.title });
        setTimeout(() => setXpToast(null), 4000);
        reloadUser(); // updates Level/XP in sidebar without page refresh

        setQuizNode(null);
    };

    const handleAddNode = (node) => {
        const updated = [...flatNodes, node];
        setFlatNodes(updated);
        rebuildGraph(updated, progressMap, quizPassedMap, selectedNode?.id);
        setShowAddNode(false);
    };

    const handleDeleteNode = async (node) => {
        if (!window.confirm(`Delete "${node.title}"?`)) return;
        try {
            await roadmapApi.deleteNode(id, node.id);
            const updated = flatNodes.filter(n => n.id !== node.id);
            setFlatNodes(updated);
            rebuildGraph(updated, progressMap, quizPassedMap, null);
            setSelectedNode(null);
        } catch (err) { alert(err.response?.data?.detail || 'Error'); }
    };

    const handlePublish = async () => {
        try { const r = await roadmapApi.publish(id); setRoadmap(r.data); }
        catch (err) { alert(err.response?.data?.detail || 'Error'); }
    };

    const handleDeleteRoadmap = async () => {
        if (!window.confirm('Are you sure you want to delete this roadmap?')) return;
        try {
            await roadmapApi.delete(id);
            navigate('/roadmaps');
        } catch (err) { alert(err.response?.data?.detail || 'Error deleting roadmap'); }
    };

    if (loading) return <div className="loading-center"><div className="spinner" /></div>;
    if (!roadmap) return null;

    const completedCount = Object.values(progressMap).filter(s => s === 'done').length;
    const pct = flatNodes.length ? Math.round((completedCount / flatNodes.length) * 100) : 0;

    // Compute effective status for the selected node (must pass isAssigned!)
    const orderedAll = [...flatNodes].sort((a, b) => (a.order_index || 0) - (b.order_index || 0));
    const selectedEffectiveStatus = selectedNode
        ? computeEffectiveStatus(selectedNode, orderedAll, progressMap, quizPassedMap, isAssigned)
        : null;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 56px)' }}>
            {/* Header */}
            <div style={{ padding: '12px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 12, background: 'var(--surface)', flexShrink: 0 }}>
                <button className="btn btn-ghost btn-sm" onClick={() => navigate('/roadmaps')}>← Back</button>
                <div style={{ flex: 1 }}>
                    <h2 style={{ fontSize: '1.1rem' }}>{roadmap.title}</h2>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 3 }}>
                        <div className="progress-bar" style={{ width: 120 }}>
                            <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-muted" style={{ fontSize: 12 }}>{completedCount}/{flatNodes.length} nodes • {pct}%</span>
                    </div>
                </div>
                {isAdmin && (
                    <div style={{ display: 'flex', gap: 8 }}>
                        <button className="btn btn-ghost btn-sm" onClick={() => setShowAddNode(true)}><Plus size={13} /> Node</button>
                        {!roadmap.is_published && <button className="btn btn-success btn-sm" onClick={handlePublish}>Publish</button>}
                        <button className="btn btn-sm" onClick={handleDeleteRoadmap} style={{ color: 'white', backgroundColor: 'var(--danger)', borderColor: 'var(--danger)' }}>
                            <Trash2 size={13} /> Delete
                        </button>
                    </div>
                )}
                {!isAdmin && !isAssigned && roadmap.is_published && (
                    <button className="btn btn-primary btn-sm" onClick={handleEnroll} disabled={enrolling} style={{ padding: '8px 20px', fontWeight: 600 }}>
                        {enrolling ? 'Enrolling…' : '🚀 Enroll'}
                    </button>
                )}
                {!isAdmin && isAssigned && (
                    <span className="badge badge-success" style={{ fontSize: 12 }}>✅ Enrolled</span>
                )}
            </div>

            {/* Main — flow + sidebar */}
            <div style={{ flex: 1, display: 'grid', gridTemplateColumns: selectedNode ? '1fr 360px' : '1fr', overflow: 'hidden' }}>
                {/* React Flow */}
                <div style={{ position: 'relative' }}>
                    <ReactFlow
                        nodes={xyNodes} edges={xyEdges}
                        onNodesChange={onXyNodesChange} onEdgesChange={onXyEdgesChange}
                        nodeTypes={nodeTypes}
                        fitView
                        style={{ background: 'var(--bg)' }}
                    >
                        <Background color="var(--border)" gap={24} />
                        <Controls style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }} />
                        <MiniMap nodeColor={n => {
                            if (n.data?.status === 'done') return 'var(--success)';
                            if (n.data?.status === 'in_progress') return 'var(--warn)';
                            return 'var(--muted)';
                        }} style={{ background: 'var(--surface)', border: '1px solid var(--border)' }} />
                    </ReactFlow>
                </div>

                {/* Sidebar */}
                {selectedNode && (
                    <div className="node-sidebar" style={{ background: 'var(--surface)' }}>
                        <div className="node-sidebar-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 600, fontSize: 13 }}>{selectedNode.title}</span>
                            <button className="btn btn-ghost btn-sm" onClick={() => setSelectedNode(null)}><X size={14} /></button>
                        </div>
                        <div className="node-sidebar-tabs">
                            <div className={`node-sidebar-tab ${sideTab === 'info' ? 'active' : ''}`} onClick={() => setSideTab('info')}><Settings size={13} /> Info</div>
                            <div className={`node-sidebar-tab ${sideTab === 'chat' ? 'active' : ''}`} onClick={() => setSideTab('chat')}><MessageSquare size={13} /> AI Tutor</div>
                        </div>
                        <div className="node-sidebar-body">
                            {sideTab === 'info'
                                ? <NodeInfoPanel
                                    node={selectedNode}
                                    effectiveStatus={selectedEffectiveStatus}
                                    onMarkDone={handleMarkDone}
                                    onMarkInProgress={handleMarkInProgress}
                                    isAdmin={isAdmin}
                                    isAssigned={isAssigned}
                                    onDelete={handleDeleteNode}
                                />
                                : <ChatPanel node={selectedNode} />
                            }
                        </div>
                    </div>
                )}
            </div>

            {/* Modals */}
            {showAddNode && <AddNodeModal roadmapId={id} nodes={flatNodes} onClose={() => setShowAddNode(false)} onAdded={handleAddNode} />}
            {quizNode && (
                <QuizModal
                    node={quizNode}
                    onClose={() => setQuizNode(null)}
                    onPassed={handleQuizPassed}
                />
            )}

            {/* XP Toast */}
            {xpToast && (
                <div style={{
                    position: 'fixed', bottom: 80, right: 24, zIndex: 9999,
                    background: 'linear-gradient(135deg, #22c55e, #16a34a)',
                    color: '#fff', padding: '14px 20px', borderRadius: 14,
                    boxShadow: '0 8px 32px rgba(34,197,94,0.4)',
                    display: 'flex', alignItems: 'center', gap: 12,
                    animation: 'slideInRight 0.35s ease',
                    minWidth: 240,
                }}>
                    <span style={{ fontSize: 28 }}>⚡</span>
                    <div>
                        <div style={{ fontWeight: 700, fontSize: 15 }}>+{xpToast.amount} XP Earned!</div>
                        <div style={{ fontSize: 12, opacity: 0.88, marginTop: 2 }}>
                            Completed: {xpToast.nodeName}
                        </div>
                    </div>
                    <button onClick={() => setXpToast(null)}
                        style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#fff', cursor: 'pointer', padding: 4 }}>
                        <X size={14} />
                    </button>
                </div>
            )}
        </div>
    );
}
