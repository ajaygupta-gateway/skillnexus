import { useEffect, useState, useCallback, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useParams, useNavigate } from 'react-router-dom';
import {
    ReactFlow, Background, Controls, MiniMap, Handle, Position,
    useNodesState, useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { roadmapApi, progressApi, chatApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { Send, CheckCircle, Clock, Lock, Plus, Trash2, BookOpen, MessageSquare, X, Settings, Edit2, Save } from 'lucide-react';

function flattenTree(nodeList) {
    const result = [];
    function walk(nodes, depth = 0) {
        // Sort siblings by order_index so indexing labels are always consistent
        const sorted = [...nodes].sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0));
        for (const node of sorted) {
            const { children, ...rest } = node;
            rest.has_children = children && children.length > 0;
            rest._depth = depth;
            result.push(rest);
            if (children && children.length > 0) walk(children, depth + 1);
        }
    }
    walk(nodeList);
    return result;
}

/* ─── Depth-aware node label helpers ─────────────────────────────── */
function toRoman(n) {
    const vals = [1000,900,500,400,100,90,50,40,10,9,5,4,1];
    const syms = ['m','cm','d','cd','c','xc','l','xl','x','ix','v','iv','i'];
    let r = '';
    for (let i = 0; i < vals.length; i++) {
        while (n >= vals[i]) { r += syms[i]; n -= vals[i]; }
    }
    return r;
}


/**
Returns the fully formatted label string for a node:
  depth 0 (root)       → "1. Title"
  depth 1 (child)      → "a. Title"
  depth 2 (grandchild) → "i. Title"
  deeper               → "1. Title" (numeric fallback)
 */
function formatNodeLabel(node) {
    const idx  = node.order_index ?? 0;
    const depth = node._depth ?? 0;
    let prefix;
    if (depth === 0)      prefix = `${idx + 1}.`;
    else if (depth === 1) prefix = `${String.fromCharCode(97 + (idx % 26))}.`;
    else if (depth === 2) prefix = `${toRoman(idx + 1)}.`;
    else                  prefix = `${idx + 1}.`;
    return `${prefix} ${node.title}`;
}

/**
 * A "header node" is a parent section with no real content to learn.
 * It organises children but has no description/resources of its own,
 * OR simply has child nodes nested under it.
 * Header nodes:
 *  - auto-derive their status from children (no manual action needed)
 *  - do NOT require a quiz to be passed
 *  - do NOT block child unlock with a quiz requirement
 */
function isHeaderNode(node) {
    return !!node.has_children;
}

/**
 * Returns true if nodeId OR any of its descendants appear in progressMap.
 * Used to determine whether a header section has been "entered" by the learner.
 */
function hasDescendantProgress(nodeId, allNodes, progressMap) {
    const children = allNodes.filter(n => n.parent_id === nodeId);
    for (const child of children) {
        if (progressMap[child.id]) return true;
        if (hasDescendantProgress(child.id, allNodes, progressMap)) return true;
    }
    return false;
}

/** ─── Compute which nodes are "unlocked" given the learning sequence ─── */
function computeEffectiveStatus(node, orderedNodes, progressMap, quizPassedMap, isAssigned) {
    if (!isAssigned) return 'locked';

    const nodeStatus = progressMap[node.id];
    if (nodeStatus === 'done') return 'done';
    
    // Parent node logic
    const children = orderedNodes.filter(n => n.parent_id === node.id);
    if (children.length > 0) {
        const allChildrenDone = children.every(c => {
            // Need recursive check to see if child is actually done (in case it's a parent too)
            const cStatus = computeEffectiveStatus(c, orderedNodes, progressMap, quizPassedMap, isAssigned);
            return cStatus === 'done';
        });
        if (allChildrenDone) return 'done';
        
        // If not all done, it is inherently locked because the user cannot manually complete it
        return 'locked';
    }

    if (nodeStatus === 'in_progress') return 'in_progress';
    
    return 'pending'; // Unlocked, not yet marked in progress
}

/* ─── Build React-Flow nodes + edges ──── */
/*
 * Layout strategy:
 *   • Root nodes are placed on a VERTICAL CENTER SPINE.
 *   • Each root's children fan out to the RIGHT side.
 *   • Sub-children fan out further to the RIGHT.
 *   • Root→Root = dashed vertical line (spine).
 *   • Parent→Child = dotted/dashed line.
 *   • Handles on nodes allow ReactFlow to draw edges.
 */
function buildGraph(nodes, progressMap, quizPassedMap, isAssigned, selectedId, onClickNode) {
    const CENTER_X = 400;
    const ROOT_GAP_Y = 120;   // minimum vertical gap between root sections
    const CHILD_GAP_Y = 60;   // vertical gap between sibling children
    const CHILD_OFFSET_X = 320; // horizontal distance from parent to children
    const SUB_CHILD_OFFSET_X = 260; // horizontal distance for deeper children

    const orderedNodes = nodes;

    // Separate roots
    const roots = nodes
        .filter(n => !n.parent_id)
        .sort((a, b) => (a.order_index || 0) - (b.order_index || 0));

    // Build a children map keyed by parent_id
    const childrenOf = {};
    nodes.forEach(n => {
        if (n.parent_id) {
            if (!childrenOf[n.parent_id]) childrenOf[n.parent_id] = [];
            childrenOf[n.parent_id].push(n);
        }
    });
    Object.values(childrenOf).forEach(arr =>
        arr.sort((a, b) => (a.order_index || 0) - (b.order_index || 0))
    );

    // Calculate the total visual height a node's subtree needs (recursive)
    function getSubtreeHeight(nodeId) {
        const kids = childrenOf[nodeId] || [];
        if (kids.length === 0) return CHILD_GAP_Y;
        let total = 0;
        kids.forEach(kid => {
            total += getSubtreeHeight(kid.id);
        });
        return total;
    }

    // Position map: nodeId → { x, y }
    const posMap = {};
    let currentY = 80;

    roots.forEach(root => {
        // Total height this root section occupies
        const sectionHeight = getSubtreeHeight(root.id);

        // Root position at center-left of its section
        posMap[root.id] = { x: CENTER_X, y: currentY + sectionHeight / 2 };

        // Place children to the right, vertically distributed across the section
        placeChildren(root.id, CENTER_X, currentY, CHILD_OFFSET_X);

        currentY += sectionHeight + ROOT_GAP_Y;
    });

    function placeChildren(parentId, parentX, startY, offsetX) {
        const kids = childrenOf[parentId] || [];
        if (kids.length === 0) return;

        let yPointer = startY;
        kids.forEach(kid => {
            const kidHeight = getSubtreeHeight(kid.id);
            const kidCenterY = yPointer + kidHeight / 2;
            const kidX = parentX + offsetX;

            posMap[kid.id] = { x: kidX, y: kidCenterY };

            // Recursively place sub-children
            placeChildren(kid.id, kidX, yPointer, SUB_CHILD_OFFSET_X);

            yPointer += kidHeight;
        });
    }

    // ── Build edges ──────────────────────────────────────────────────────

    const xyEdges = [];

    // Root-to-root spine (dashed vertical)
    for (let i = 0; i < roots.length - 1; i++) {
        xyEdges.push({
            id: `e-spine-${roots[i].id}-${roots[i + 1].id}`,
            source: roots[i].id,
            target: roots[i + 1].id,
            sourceHandle: 'bottom',
            targetHandle: 'top',
            type: 'smoothstep',
            style: { stroke: 'var(--primary)', strokeWidth: 3, strokeDasharray: '8,6' },
            animated: false,
        });
    }

    // Find map of which nodes have children
    const hasChildrenMap = {};
    nodes.forEach(n => {
        if (n.parent_id) hasChildrenMap[n.parent_id] = true;
    });

    // Parent-to-child connections (dotted)
    nodes.filter(n => n.parent_id).forEach(n => {
        const isInProgress = progressMap[n.id] === 'in_progress';
        const isDone = progressMap[n.id] === 'done';
        const isHighlightedEdge = selectedId && hasChildrenMap[selectedId] && n.parent_id === selectedId;

        xyEdges.push({
            id: `e-${n.parent_id}-${n.id}`,
            source: n.parent_id,
            target: n.id,
            sourceHandle: 'right',
            targetHandle: 'left',
            type: 'smoothstep',
            style: isHighlightedEdge
                ? { stroke: '#db2777', strokeWidth: 4, strokeDasharray: '8,6' }
                : {
                    stroke: isDone ? 'var(--success)' : isInProgress ? 'var(--warn)' : 'var(--muted)',
                    strokeWidth: 3,
                    strokeDasharray: '5,5',
                },
            animated: isInProgress || isHighlightedEdge,
            zIndex: isHighlightedEdge ? 10 : 0,
        });
    });

    // ── Build ReactFlow nodes ────────────────────────────────────────────

    const xyNodes = nodes.map(n => {
        const effectiveStatus = computeEffectiveStatus(n, orderedNodes, progressMap, quizPassedMap, isAssigned);
        const isRoot = !n.parent_id;
        const pos = posMap[n.id] || { x: 0, y: 0 };

        const isHighlightedNode = selectedId && hasChildrenMap[selectedId] && (n.id === selectedId || n.parent_id === selectedId);

        return {
            id: n.id,
            type: 'roadmapNode',
            position: {
                x: n.position_x !== 0 ? n.position_x : pos.x,
                y: n.position_y !== 0 ? n.position_y : pos.y,
            },
            data: {
                label: formatNodeLabel(n),
                status: effectiveStatus,
                selected: n.id === selectedId,
                highlighted: isHighlightedNode,
                isRoot,
                isHeader: isHeaderNode(n),
                depth: n._depth || 0,
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
    const [quizSel, setQuizSel] = useState({});
    const [quizResult, setQuizResult] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(false);   // quiz generation failed
    const [submitError, setSubmitError] = useState('');  // submission error message
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setLoadError(false);
        chatApi.generateQuiz(node.id, node.roadmap_id)
            .then(r => { if (!cancelled) setQuiz(r.data); })
            .catch(() => { if (!cancelled) setLoadError(true); })
            .finally(() => { if (!cancelled) setLoading(false); });
        // Cleanup: if StrictMode re-runs the effect, ignore the first response
        return () => { cancelled = true; };
    }, [node.id, node.roadmap_id]);

    const allAnswered = quiz && Object.keys(quizSel).length >= quiz.questions.length;

    const submit = async () => {
        if (submitting) return; // guard against accidental double-click
        setSubmitting(true);
        setSubmitError('');
        try {
            const answers = {};
            quiz.questions.forEach(q => {
                answers[String(q.question_number)] = quizSel[String(q.question_number)] || '';
            });
            const r = await chatApi.submitQuiz(node.id, node.roadmap_id, { answers });
            setQuizResult(r.data);
            if (r.data.passed) {
                setTimeout(() => onPassed(), 1800);
            }
        } catch {
            setSubmitError('Something went wrong while submitting. Please try again.');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                    <h2 style={{ margin: 0 }}>🧠 Node Quiz: {node.title}</h2>
                    <button className="btn btn-ghost btn-sm" onClick={onClose}><X size={14} /></button>
                </div>

                {/* ── Quiz generation failed ── */}
                {loadError && (
                    <div style={{ textAlign: 'center', padding: '24px 0' }}>
                        <p style={{ fontSize: 32, marginBottom: 12 }}>😔</p>
                        <p style={{ fontWeight: 600, fontSize: 15, marginBottom: 6 }}>Couldn't generate quiz</p>
                        <p className="text-muted" style={{ fontSize: 13, marginBottom: 20 }}>
                            We ran into a problem preparing questions for this topic.
                            Please try again in a moment.
                        </p>
                        <div className="modal-footer" style={{ justifyContent: 'center' }}>
                            <button className="btn btn-ghost" onClick={onClose}>Close</button>
                            <button className="btn btn-primary" onClick={() => {
                                setLoadError(false);
                                setLoading(true);
                                chatApi.generateQuiz(node.id, node.roadmap_id)
                                    .then(r => setQuiz(r.data))
                                    .catch(() => setLoadError(true))
                                    .finally(() => setLoading(false));
                            }}>Retry</button>
                        </div>
                    </div>
                )}

                {/* ── Loading spinner ── */}
                {loading && !loadError && (
                    <div style={{ textAlign: 'center', padding: '24px 0' }}>
                        <div className="loading-center"><div className="spinner" /></div>
                        <p className="text-muted" style={{ fontSize: 13, marginTop: 12 }}>Generating quiz questions…</p>
                    </div>
                )}

                {/* ── Quiz questions ── */}
                {!loading && !loadError && quiz && !quizResult && (
                    <>
                        <p className="text-muted" style={{ fontSize: 13, marginBottom: 16 }}>
                            Answer at least 2 questions correctly to unlock the next node.
                        </p>
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
                        {submitError && (
                            <div style={{ background: 'rgba(239,68,68,.1)', border: '1px solid var(--danger)', borderRadius: 8, padding: '10px 14px', marginBottom: 12, fontSize: 13, color: 'var(--danger)' }}>
                                {submitError}
                            </div>
                        )}
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

                {/* ── Quiz result ── */}
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
                {messages.filter(m => !m.content.startsWith("__QUIZ_ANSWERS__")).map((m, i) => (
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
function NodeInfoPanel({ node, effectiveStatus, onMarkDone, onMarkInProgress, isAdmin, onDelete, isAssigned, onEdit }) {
    const [saving, setSaving] = useState(false);
    const isHeader = isHeaderNode(node);

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

                    {isHeader ? (
                        effectiveStatus === 'done' ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--success)', fontSize: 13, padding: '8px 0' }}>
                                <CheckCircle size={16} /> <strong>Section Complete!</strong>
                            </div>
                        ) : (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'var(--surface2)', borderRadius: 8, border: '1px solid var(--border)' }}>
                                <BookOpen size={14} color="var(--primary-h)" />
                                <span style={{ fontSize: 13, color: 'var(--muted)' }}>
                                    This section completes automatically when all sub-topics are finished.
                                </span>
                            </div>
                        )
                    ) : effectiveStatus === 'locked' ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'var(--surface2)', borderRadius: 8, border: '1px solid var(--border)' }}>
                            <Lock size={14} color="var(--muted)" />
                            <span style={{ fontSize: 13, color: 'var(--muted)' }}>
                                You must complete all sub-topics (child nodes) first to unlock this section.
                            </span>
                        </div>
                    ) : effectiveStatus === 'done' ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--success)', fontSize: 13, padding: '8px 0' }}>
                            <CheckCircle size={16} /> <strong>Completed!</strong>
                        </div>
                    ) : (
                        /* Unlocked node — show action buttons */
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                            <button className="btn btn-ghost btn-sm" disabled={saving || effectiveStatus === 'in_progress'}
                                onClick={async () => { setSaving(true); await onMarkInProgress(node); setSaving(false); }}>
                                <Clock size={13} /> {effectiveStatus === 'in_progress' ? 'In Progress' : 'Mark In Progress'}
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
                <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                    <button className="btn btn-ghost btn-sm" style={{ color: 'var(--primary)', borderColor: 'var(--primary)' }}
                        onClick={() => onEdit(node)}>
                        <Edit2 size={13} /> Edit Node
                    </button>
                    <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)', borderColor: 'var(--danger)' }}
                        onClick={() => onDelete(node)}>
                        <Trash2 size={13} /> Delete Node
                    </button>
                </div>
            )}
        </div>
    );
}

/* ─── Edit Node Modal ─────────────────────────────────────────────────── */
function EditNodeModal({ roadmapId, node, nodes, onClose, onEdited }) {
    const [form, setForm] = useState({ 
        title: node.title || '', 
        description: node.description || '', 
        parent_id: node.parent_id || '',
        order_index: node.order_index ?? 0,
    });
    const [resources, setResources] = useState(
        Array.isArray(node.resources) ? node.resources.map(r => ({ title: r.title || '', url: r.url || '', type: r.type || 'article' })) : []
    );
    const [saving, setSaving] = useState(false);

    const submit = async (e) => {
        e.preventDefault(); setSaving(true);
        try {
            const validResources = resources.filter(r => r.title.trim() && r.url.trim());
            const payload = { 
                title: form.title,
                description: form.description || null,
                parent_id: form.parent_id || null,
                order_index: Number(form.order_index),
                resources: validResources,
            };
            const r = await roadmapApi.updateNode(roadmapId, node.id, payload);
            onEdited(r.data);
        } catch (err) { alert(err.response?.data?.detail || 'Error'); }
        finally { setSaving(false); }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal" style={{ maxWidth: 580, maxHeight: '85vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
                <h2>Edit Node</h2>
                <form onSubmit={submit}>
                    <div className="form-group"><label>Title <span style={{ color: 'var(--danger)' }}>*</span></label><input className="input" required autoFocus value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} /></div>
                    <div className="form-group"><label>Description</label><textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} style={{ minHeight: 72 }} /></div>
                    <div className="form-group">
                        <label>Parent Node <span className="text-muted" style={{ fontSize: 12 }}>(optional)</span></label>
                        <select value={form.parent_id} onChange={e => setForm(p => ({ ...p, parent_id: e.target.value }))}>
                            <option value="">— Root (no parent) —</option>
                            {nodes.filter(n => n.id !== node.id).map(n => <option key={n.id} value={n.id}>{n.title}</option>)}
                        </select>
                    </div>
                    <div className="form-group">
                        <label>Order / Position among siblings</label>
                        <input className="input" type="number" min="0" value={form.order_index}
                            onChange={e => setForm(p => ({ ...p, order_index: e.target.value }))}
                            style={{ width: 90 }}
                        />
                    </div>
                    <ResourceEditor resources={resources} onChange={setResources} />
                    <div className="modal-footer">
                        <button className="btn btn-ghost" type="button" onClick={onClose}>Cancel</button>
                        <button className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save Changes'}</button>
                    </div>
                </form>
            </div>
        </div>
    );
}

/* ─── Resource Row Editor ─────────────────────────────────────────────── */
function ResourceEditor({ resources, onChange }) {
    const add = () => onChange([...resources, { title: '', url: '', type: 'article' }]);
    const remove = (i) => onChange(resources.filter((_, idx) => idx !== i));
    const update = (i, field, val) => onChange(resources.map((r, idx) => idx === i ? { ...r, [field]: val } : r));

    return (
        <div className="form-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <label style={{ marginBottom: 0 }}>Resources</label>
                <button type="button" className="btn btn-ghost btn-sm" onClick={add} style={{ fontSize: 12 }}>+ Add Resource</button>
            </div>
            {resources.length === 0 && (
                <p className="text-muted" style={{ fontSize: 12, marginBottom: 4 }}>No resources yet. Click "+ Add Resource" to add links.</p>
            )}
            {resources.map((r, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto auto', gap: 6, marginBottom: 8, alignItems: 'center' }}>
                    <input className="input" placeholder="Title" value={r.title} onChange={e => update(i, 'title', e.target.value)} style={{ fontSize: 12, padding: '6px 10px' }} />
                    <input className="input" placeholder="URL (https://…)" value={r.url} onChange={e => update(i, 'url', e.target.value)} style={{ fontSize: 12, padding: '6px 10px' }} />
                    <select value={r.type} onChange={e => update(i, 'type', e.target.value)} style={{ fontSize: 12, padding: '6px 8px', background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)' }}>
                        <option value="article">Article</option>
                        <option value="video">Video</option>
                        <option value="docs">Docs</option>
                        <option value="course">Course</option>
                    </select>
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => remove(i)} style={{ color: 'var(--danger)', borderColor: 'var(--danger)', padding: '4px 8px' }}>✕</button>
                </div>
            ))}
        </div>
    );
}

/* ─── Add Node Modal ─────────────────────────────────────────────────── */
function AddNodeModal({ roadmapId, nodes, onClose, onAdded }) {
    // Auto-compute order_index: count existing siblings (nodes without a parent, or with same parent)
    const computeDefaultOrderIndex = (parentId) => {
        const siblings = nodes.filter(n => (n.parent_id || '') === (parentId || ''));
        return siblings.length; // next available index (0-based)
    };

    const [form, setForm] = useState({ title: '', description: '', parent_id: '', order_index: computeDefaultOrderIndex('') });
    const [resources, setResources] = useState([]);
    const [saving, setSaving] = useState(false);

    // Recompute order_index whenever parent_id changes
    const handleParentChange = (e) => {
        const pid = e.target.value;
        setForm(p => ({ ...p, parent_id: pid, order_index: computeDefaultOrderIndex(pid) }));
    };

    const submit = async (e) => {
        e.preventDefault(); setSaving(true);
        try {
            // Validate resources: title + url are required for each
            const validResources = resources.filter(r => r.title.trim() && r.url.trim());
            const payload = {
                title: form.title,
                description: form.description || null,
                parent_id: form.parent_id || null,
                order_index: Number(form.order_index),
                resources: validResources,
            };
            const r = await roadmapApi.addNode(roadmapId, payload);
            onAdded(r.data);
        } catch (err) { alert(err.response?.data?.detail || 'Error'); }
        finally { setSaving(false); }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal" style={{ maxWidth: 580, maxHeight: '85vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
                <h2>Add Node</h2>
                <form onSubmit={submit}>
                    <div className="form-group"><label>Title <span style={{ color: 'var(--danger)' }}>*</span></label><input className="input" required autoFocus value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} /></div>
                    <div className="form-group"><label>Description</label><textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} style={{ minHeight: 72 }} /></div>
                    <div className="form-group">
                        <label>Parent Node <span className="text-muted" style={{ fontSize: 12 }}>(optional)</span></label>
                        <select value={form.parent_id} onChange={handleParentChange}>
                            <option value="">— Root (no parent) —</option>
                            {nodes.map(n => <option key={n.id} value={n.id}>{n.title}</option>)}
                        </select>
                    </div>
                    <div className="form-group">
                        <label>Order / Position among siblings</label>
                        <input className="input" type="number" min="0" value={form.order_index}
                            onChange={e => setForm(p => ({ ...p, order_index: e.target.value }))}
                            style={{ width: 90 }}
                        />
                        <p className="text-muted" style={{ fontSize: 11, marginTop: 4 }}>0 = first among siblings. Auto-set to next available index.</p>
                    </div>
                    <ResourceEditor resources={resources} onChange={setResources} />
                    <div className="modal-footer">
                        <button className="btn btn-ghost" type="button" onClick={onClose}>Cancel</button>
                        <button className="btn btn-primary" disabled={saving}>{saving ? 'Adding…' : 'Add Node'}</button>
                    </div>
                </form>
            </div>
        </div>
    );
}

/* ─── Custom node component */
function RoadmapNode({ data }) {
    const s = data.status || 'locked';
    const statusColors = {
        done: 'var(--success)',
        in_progress: 'var(--primary)',
        pending: 'var(--muted)',
        locked: 'var(--muted)',
    };
    const dotColor = statusColors[s];
    const hlClass = data.highlighted ? 'highlighted-node' : '';

    // Invisible handles for edge connections
    const handleStyle = { opacity: 0, width: 6, height: 6, minWidth: 0, minHeight: 0 };

    // Root / section header nodes — large prominent pill
    if (data.isRoot) {
        return (
            <div
                className={`sn-node sn-root ${data.selected ? 'selected' : ''} ${hlClass} status-${s}`}
                onClick={data.onClick}
            >
                <Handle type="target" position={Position.Top} id="top" style={handleStyle} />
                <Handle type="source" position={Position.Bottom} id="bottom" style={handleStyle} />
                <Handle type="source" position={Position.Right} id="right" style={handleStyle} />
                <Handle type="target" position={Position.Left} id="left" style={handleStyle} />
                <div className="node-title">{data.label}</div>
                {s === 'done' ? (
                    <CheckCircle size={16} />
                ) : (
                    <div className="sn-status-dot" style={{ background: dotColor }} />
                )}
            </div>
        );
    }

    // Header nodes (parents with children, but not root)
    if (data.isHeader) {
        return (
            <div
                className={`sn-node sn-header ${data.selected ? 'selected' : ''} ${hlClass} status-${s}`}
                onClick={data.onClick}
            >
                <Handle type="target" position={Position.Top} id="top" style={handleStyle} />
                <Handle type="source" position={Position.Bottom} id="bottom" style={handleStyle} />
                <Handle type="source" position={Position.Right} id="right" style={handleStyle} />
                <Handle type="target" position={Position.Left} id="left" style={handleStyle} />
                <div className="sn-status-dot" style={{ background: dotColor }} />
                <div className="node-title">{data.label}</div>
                <div className="sn-status-dot" style={{ background: dotColor }} />
            </div>
        );
    }

    // Leaf / content nodes — small pill shape
    return (
        <div
            className={`sn-node sn-leaf ${data.selected ? 'selected' : ''} ${hlClass} status-${s}`}
            onClick={data.onClick}
        >
            <Handle type="target" position={Position.Top} id="top" style={handleStyle} />
            <Handle type="source" position={Position.Bottom} id="bottom" style={handleStyle} />
            <Handle type="source" position={Position.Right} id="right" style={handleStyle} />
            <Handle type="target" position={Position.Left} id="left" style={handleStyle} />
            <div className="sn-status-dot" style={{ background: dotColor }} />
            <div className="node-title">{data.label}</div>
            <div className="sn-status-dot" style={{ background: dotColor }} />
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
    const [showEditNode, setShowEditNode] = useState(false);
    const [quizNode, setQuizNode] = useState(null);
    const [loading, setLoading] = useState(true);
    const [xpToast, setXpToast] = useState(null); // { amount: 25, nodeName: '...' }
    const [modifiedPositions, setModifiedPositions] = useState({});
    const [savingPositions, setSavingPositions] = useState(false);

    const [xyNodes, setXyNodes, onXyNodesChange] = useNodesState([]);
    const [xyEdges, setXyEdges, onXyEdgesChange] = useEdgesState([]);

    const rebuildGraph = useCallback((nodes, pMap, qMap, selId, assigned) => {
        const { xyNodes: nn, xyEdges: ee } = buildGraph(nodes, pMap, qMap, assigned ?? isAssigned, selId, n => {
            setSelectedNode(n); setSideTab('info');
            rebuildGraph(nodes, pMap, qMap, n.id, assigned ?? isAssigned);
        });
        setXyNodes(nn); setXyEdges(ee);
    }, [isAssigned]);

    const handleCloseSidebar = () => {
        setSelectedNode(null);
        rebuildGraph(flatNodes, progressMap, quizPassedMap, null, isAssigned);
    };

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

    // ── Recursively auto-complete parent nodes ──────────────────────────────
    const checkAndAutoCompleteParent = async (completedNodeId, currentPMap, currentQMap) => {
        const completedNode = flatNodes.find(n => n.id === completedNodeId);
        if (!completedNode?.parent_id) return { pMap: currentPMap, qMap: currentQMap };

        const parent = flatNodes.find(n => n.id === completedNode.parent_id);
        if (!parent) return { pMap: currentPMap, qMap: currentQMap };

        const siblings = flatNodes.filter(n => n.parent_id === parent.id);
        // We know a sibling is done if currentPMap says 'done', or if it's a parent that auto-resolved to done.
        const allSiblingsDone = siblings.every(s => {
            const status = computeEffectiveStatus(s, flatNodes, currentPMap, currentQMap, isAssigned);
            return status === 'done' || currentPMap[s.id] === 'done';
        });

        if (allSiblingsDone && currentPMap[parent.id] !== 'done') {
            try {
                await progressApi.updateNode(parent.roadmap_id, parent.id, { status: 'done', bypass_quiz: true });
            } catch { /* parent might already be done */ }
            const newPMap = { ...currentPMap, [parent.id]: 'done' };
            const newQMap = { ...currentQMap, [parent.id]: true };

            // Recurse upwards to grand-parent
            return await checkAndAutoCompleteParent(parent.id, newPMap, newQMap);
        }
        return { pMap: currentPMap, qMap: currentQMap };
    };

    const markNodeCompleted = async (completedNode, bypassQuiz = false) => {
        // 1. Mark the completed node as 'done' in the backend, pass bypass_quiz if applicable
        try {
            await progressApi.updateNode(completedNode.roadmap_id, completedNode.id, { 
                status: 'done', 
                bypass_quiz: bypassQuiz 
            });
        } catch {
            // If already done, fine
        }

        // 2. Update local state: node is done + quiz passed
        let newPMap = { ...progressMap, [completedNode.id]: 'done' };
        let newQMap = { ...quizPassedMap, [completedNode.id]: true };

        // 2a. Auto-complete parent headers recursively if all their children are now done
        const parentResult = await checkAndAutoCompleteParent(completedNode.id, newPMap, newQMap);
        newPMap = parentResult.pMap;
        newQMap = parentResult.qMap;

        setProgressMap(newPMap);
        setQuizPassedMap(newQMap);
        rebuildGraph(flatNodes, newPMap, newQMap, selectedNode?.id);

        // 3. Show XP toast only when ALL root nodes are completed in this specific update
        const rootNodes = flatNodes.filter(n => !n.parent_id);
        const rootCount = rootNodes.length || 1;
        const previousDoneRootCount = rootNodes.filter(n => progressMap[n.id] === 'done').length;
        const currentDoneRootCount = rootNodes.filter(n => newPMap[n.id] === 'done').length;

        // Trigger toast only exactly when transitioning to fully completed
        if (currentDoneRootCount === rootCount && previousDoneRootCount < rootCount) {
            setXpToast({ amount: 50, nodeName: "Entire Roadmap" });
            setTimeout(() => setXpToast(null), 4000);
        }
        reloadUser();
    };

    // Called when learner clicks "Mark as Done"
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

    // Called when quiz is passed from modal — NOW mark node as done
    const handleQuizPassed = async () => {
        if (!quizNode) return;
        await markNodeCompleted(quizNode, false);
        setQuizNode(null);
    };

    const handleAddNode = async () => {
        // Re-fetch the full roadmap tree so flattenTree can assign correct _depth,
        // has_children, and order_index-sorted siblings for all nodes.
        setShowAddNode(false);
        await load();
    };

    const handleEditNode = async (updatedNode) => {
        // Re-fetch so the tree is fully rebuilt with correct depth/index metadata.
        setShowEditNode(false);
        setSelectedNode(null);
        await load();
    };

    const handleNodeDragStop = useCallback((event, node) => {
        if (!isAdmin) return;
        setFlatNodes(prev => prev.map(n => n.id === node.id ? { ...n, position_x: node.position.x, position_y: node.position.y } : n));
        setModifiedPositions(prev => ({ 
            ...prev, 
            [node.id]: { position_x: node.position.x, position_y: node.position.y } 
        }));
    }, [isAdmin]);

    const handleSavePositions = async () => {
        const nodeIds = Object.keys(modifiedPositions);
        if (nodeIds.length === 0) return;
        setSavingPositions(true);
        try {
            await Promise.all(nodeIds.map(nodeId => 
                roadmapApi.updateNode(id, nodeId, modifiedPositions[nodeId])
            ));
            setModifiedPositions({});
        } catch (err) {
            alert('Failed to save some node positions.');
        } finally {
            setSavingPositions(false);
        }
    };

    const handleDeleteNode = async (node) => {
        if (!window.confirm(`Delete "${node.title}"?`)) return;
        try {
            await roadmapApi.deleteNode(id, node.id);
            const updated = flatNodes.filter(n => n.id !== node.id);
            setFlatNodes(updated);
            setSelectedNode(null);
            rebuildGraph(updated, progressMap, quizPassedMap, null);
        } catch (err) { alert(err.response?.data?.detail || 'Error'); }
    };

    const handlePublish = async () => {
        try {
            await roadmapApi.publish(id);
            navigate('/roadmaps');
        }
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

    // Compute effective status for the selected node.
    // flatNodes is already in preorder DFS learning order — do NOT re-sort.
    const selectedEffectiveStatus = selectedNode
        ? computeEffectiveStatus(selectedNode, flatNodes, progressMap, quizPassedMap, isAssigned)
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
                        {Object.keys(modifiedPositions).length > 0 && (
                            <button className="btn btn-primary btn-sm" onClick={handleSavePositions} disabled={savingPositions}>
                                <Save size={13} /> {savingPositions ? 'Saving...' : 'Save Positions'}
                            </button>
                        )}
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
                        onNodeDragStop={handleNodeDragStop}
                        onPaneClick={handleCloseSidebar}
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
                            <button className="btn btn-ghost btn-sm" onClick={handleCloseSidebar}><X size={14} /></button>
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
                                    onEdit={() => setShowEditNode(true)}
                                />
                                : <ChatPanel node={selectedNode} />
                            }
                        </div>
                    </div>
                )}
            </div>

            {/* Modals */}
            {showAddNode && <AddNodeModal roadmapId={id} nodes={flatNodes} onClose={() => setShowAddNode(false)} onAdded={handleAddNode} />}
            {showEditNode && selectedNode && (
                <EditNodeModal 
                    roadmapId={id} 
                    node={selectedNode} 
                    nodes={flatNodes} 
                    onClose={() => setShowEditNode(false)} 
                    onEdited={handleEditNode} 
                />
            )}
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