# SkillNexus: Roadmap Graph & Node Completion Flow

This document explains every layer of the system — from the graph rendering library to the
database — covering the full journey of a user completing a node with a quiz.

---

## Part 1: The Graph Library — React Flow

### What is it?
The roadmap graph is powered by **`@xyflow/react`** (also known as **React Flow**).  
It is a React library specifically designed for building interactive node-based UIs like
flowcharts, diagrams, and roadmaps.

**npm package:** `@xyflow/react`  
**Used in:** `frontend/skill-nexus/src/pages/RoadmapDetail.jsx`

```jsx
import {
    ReactFlow, Background, Controls, MiniMap, Handle, Position,
    useNodesState, useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
```

### What React Flow gives us:
| Feature | Used in SkillNexus |
|---|---|
| `ReactFlow` | The main canvas component that renders the graph |
| `useNodesState` | State management for all nodes (position, data, style) |
| `useEdgesState` | State management for all connecting lines (edges) |
| `Handle` | The invisible connection points on each node |
| `Background` | The dot/grid background pattern |
| `Controls` | Zoom in, zoom out, fit-to-screen controls |
| `MiniMap` | The small overview map in the corner |

### Custom Node Types
React Flow allows fully custom node components. SkillNexus defines 3 types:

| Type | Component | Visual Role |
|---|---|---|
| `sn-root` | `RoadmapNode (isRoot=true)` | Big pill — Top-level section header |
| `sn-header` | `RoadmapNode (isHeader=true)` | Medium pill — Sub-section with children |
| `sn-leaf` | `RoadmapNode (isHeader=false)` | Small pill — Actual learning topic |

All three are registered in one line:
```jsx
const nodeTypes = { roadmapNode: RoadmapNode };
<ReactFlow nodeTypes={nodeTypes} ... />
```

---

## Part 2: Page Load — Fetching Data

When a user navigates to `/roadmaps/:id`, the `RoadmapDetail` page load sequence begins:

### Step 1: Fetch Roadmap + Nodes
```
Frontend calls:
  GET /api/v1/roadmaps/{id}

Backend (roadmaps.py route → RoadmapService):
  - Fetches the roadmap from PostgreSQL
  - Recursively builds the full nested tree of nodes
  - Returns: { id, title, nodes: [ { id, title, children: [ ... ] } ] }
```

The API returns a **nested tree** (parents contain children). The frontend
flattens this into a simple array using `flattenTree()`:
```js
// [ { id, title, parent_id, has_children, _depth }, ... ]
const nodes = flattenTree(r.data.nodes || []);
```

### Step 2: Fetch User Progress
```
Frontend calls:
  GET /api/v1/progress/roadmaps/{id}

Backend (progress.py route → ProgressService.get_roadmap_progress()):
  - Checks: is the user assigned to this roadmap?
  - If NOT assigned → returns 403 → frontend sets isAssigned = false
  - If assigned → returns { node_statuses: [ { node_id, status, quiz_passed } ] }

Frontend builds two maps:
  progressMap  = { "node-uuid": "in_progress" | "done" }
  quizPassedMap = { "node-uuid": true | false }
```

### Step 3: Build the Graph
The frontend calls `buildGraph()` which:
1. Positions all nodes using a **custom layout algorithm** (not from React Flow):
   - Root nodes → center vertical spine
   - Children → fan out to the right
   - Sub-children → fan out further right
2. Creates **React Flow node objects** with status colors
3. Creates **React Flow edge objects** (the connecting lines)
4. Sets them into state with `setXyNodes()` and `setXyEdges()`

```
Node colors by status:
  done        → green  (var(--success))
  in_progress → blue   (var(--primary))
  pending     → gray   (var(--muted))
  locked      → gray   (var(--muted))

Edge styles:
  Root → Root       : dashed vertical spine (purple)
  Parent → Children : dotted lines (color follows child status)
```

---

## Part 3: User Actions on a Node

### Click a Node
```
User clicks a node bubble in the graph
  ↓
onClick() is called → setSelectedNode(node)
  ↓
rebuildGraph() re-renders to highlight selected node
  ↓
Sidebar opens (right panel) showing:
  - Node title & description
  - Status buttons (Mark In Progress / Mark as Done)
  - Resources (links to articles, videos)
  - AI Tutor chat panel
```

### Mark In Progress
```
User clicks "Mark In Progress"
  ↓
Frontend calls:
  POST /api/v1/progress/roadmaps/{rid}/nodes/{nid}
  Body: { "status": "in_progress" }

Backend:
  Validates user is enrolled → upserts UserNodeProgress row → status = 'in_progress'

Frontend:
  Updates progressMap locally → rebuildGraph() → node turns blue
```

---

## Part 4: The Complete "Mark as Done" + Quiz Flow

This is the most complex flow in the entire application.

### Step 1 — User clicks "Mark as Done"
```jsx
// NodeInfoPanel.jsx (inside RoadmapDetail.jsx)
<button onClick={() => onMarkDone(node)}>Mark as Done</button>

// handleMarkDone() in RoadmapDetail
const handleMarkDone = (node) => {
    setQuizNode(node); // ← Just opens the Quiz Modal, nothing else
};
```

### Step 2 — Quiz Modal Opens → Generate Quiz
```
Frontend calls:
  POST /api/v1/chat/sessions/{node_id}/quiz?roadmap_id={rid}

Backend (chat.py → ChatService.generate_quiz()):
  1. Fetches node title + description from PostgreSQL
  2. Builds this prompt for the LLM:
       "Generate exactly 3 multiple-choice quiz questions to test
        understanding of: '{node.title}'.
        Each question must have exactly 4 options (A, B, C, D).
        Vary difficulty: 1 easy, 1 medium, 1 hard."

  3. Calls LLM via get_structured_llm(_QuizSchema)
       → Forces the LLM to return strict JSON using Pydantic schema
       → _QuizSchema enforces: exactly 3 questions, exactly 4 options, correct_answer field

  4. Correct answers are saved to PostgreSQL (chat_messages table):
       role    = 'system'
       content = '__QUIZ_ANSWERS__:{"1":"B","2":"A","3":"D"}'
       (This message is NEVER sent to the frontend)

  5. Returns to frontend (WITHOUT the answers):
       { questions: [ { question_number, question, options: [A,B,C,D] } ] }
```

### Step 3 — User Answers and Submits
```
User selects options A/B/C/D for each question
  ↓
Frontend calls:
  POST /api/v1/chat/sessions/{node_id}/quiz/submit?roadmap_id={rid}
  Body: { "answers": { "1": "B", "2": "A", "3": "C" } }

Backend (chat.py → ChatService.submit_quiz()):
  1. Loads chat history for this session
  2. Scans messages in REVERSE to find the latest __QUIZ_ANSWERS__ message
  3. Parses correct answers: {"1":"B","2":"A","3":"D"}
  4. Grades: submitted["1"]="B" == correct["1"]="B" → ✅
             submitted["2"]="A" == correct["2"]="A" → ✅
             submitted["3"]="C" != correct["3"]="D" → ❌
  5. Score = 2/3 → passed = (score >= 2) → True ✅

  6. If passed:
       → Updates user_node_progress: quiz_passed = true
       → Sets can_mark_done = true in response

  7. Returns:
       { score: 2, total: 3, passed: true, can_mark_done: true, feedback: "🎉 Excellent!..." }
```

### Step 4 — Quiz Passed → Mark Node Done
```
Frontend receives passed = true
  ↓
After 1.8 second delay (so user sees the "Passed!" message):
  onPassed() is called → handleQuizPassed()
  ↓
markNodeCompleted(quizNode, bypassQuiz=false) is called:

  API Call:
    POST /api/v1/progress/roadmaps/{rid}/nodes/{node_id}
    Body: { "status": "done", "bypass_quiz": false }

  Backend (progress.py → ProgressService.update_node_progress()):
    - Verifies user is enrolled
    - Validates quiz_passed = true (since bypass_quiz=false)
    - Upserts UserNodeProgress: status = 'done'
    - Calls _auto_complete_parents() (see Step 5)
    - Checks: are ALL root nodes now done?
        If yes → awards 50 XP via add_xp() → PointTransaction saved to PostgreSQL
    - Recalculates assignment completion percentage

  Frontend updates progressMap: { [node_id]: 'done' }
  Frontend updates quizPassedMap: { [node_id]: true }
```

### Step 5 — Auto-Complete Parent Sections (Backend)
```
_auto_complete_parents() runs on the backend within the same DB transaction:

  For each ancestor going upward:
    1. Check: does this parent have resources?
       → If YES: STOP. Parent requires its own quiz (user must mark it done manually).
       → If NO: continue.

    2. Check: are ALL children of this parent now "done"?
       → If YES: auto-set parent to "done" (bypass_quiz=true)
       → If NO: STOP.

    3. Recurse upward to the grandparent.

  Key Rule:
    Parent WITH resources → requires manual quiz completion
    Parent WITHOUT resources → auto-completes when all children are done
```

### Step 6 — Graph Re-renders
```
Frontend calls load() to re-fetch all data from backend
  ↓
React Flow receives updated node objects
  ↓
computeEffectiveStatus() determines visual status:
  - For leaf nodes: uses progressMap directly
  - For header nodes WITHOUT resources: "done" if all children done
  - For header nodes WITH resources: "done" only if quiz_passed
  ↓
Completed nodes get a green CheckCircle icon
Parent sections auto-turn green if all children done
Spine edges animate in green
```

### Step 7 — XP Toast (if roadmap fully complete)
```js
// Only when ALL root nodes are now done AND they weren't before
if (currentDoneRootCount === rootCount && previousDoneRootCount < rootCount) {
    setXpToast({ amount: 50, nodeName: "Entire Roadmap" });
    setTimeout(() => setXpToast(null), 4000);
}
reloadUser(); // Refreshes XP/level in the sidebar
```

---

## Part 5: Enrollment Flow

### Self-Enrollment (Learner)
```
User clicks "Enroll" on a published roadmap
  ↓
POST /api/v1/progress/roadmaps/{id}/enroll
  ↓
Backend (ProgressService.enroll_roadmap()):
  1. Creates UserRoadmapAssignment record (strict_mode=true)
  2. Initializes first root node as 'in_progress'
  ↓
User sees roadmap with first node unlocked
```

### Admin Assignment
```
Admin assigns roadmap via Control Center
  ↓
POST /api/v1/admin/assignments
  Body: { user_ids: [...], roadmap_id: "..." }
  ↓
Backend (ProgressService.create_assignment()):
  1. Creates UserRoadmapAssignment for each user (strict_mode=true)
  2. Initializes first root node as 'in_progress' for each user
  ↓
Learner sees roadmap as enrolled with first node ready
```

### Admin Un-assignment
```
Admin removes assignment via Control Center
  ↓
DELETE /api/v1/admin/assignments/{id}
  ↓
Backend (ProgressService.delete_assignment()):
  1. Deletes ALL UserNodeProgress records for user + roadmap
  2. Deletes the UserRoadmapAssignment record
  ↓
Learner is fully unenrolled (clean slate)
```

---

## Part 6: Published Roadmap Restrictions

Once an admin publishes a roadmap, the following are **blocked**:

| Action | Allowed? |
|---|---|
| Edit roadmap title/description | ❌ Blocked |
| Add new nodes | ❌ Blocked |
| Delete nodes | ❌ Blocked |
| Edit node content | ❌ Blocked |
| Move node positions (drag) | ✅ Allowed |
| Delete entire roadmap | ❌ Blocked |

Enforced on both backend (400 error) and frontend (buttons hidden).

---

## Part 7: Complete Flow Diagram

```
User navigates to /roadmaps/:id
        │
        ├─► GET /roadmaps/{id}          → PostgreSQL: roadmaps + roadmap_nodes
        ├─► GET /progress/roadmaps/{id} → PostgreSQL: user_node_progress
        │
        ▼
React Flow renders graph (buildGraph)
        │
        ▼
User clicks a node → Sidebar opens
        │
        ├─► "Mark In Progress"
        │     └─► POST /progress/.../nodes/{id} { status: "in_progress" }
        │           └─► PostgreSQL: upserts user_node_progress
        │
        └─► "Mark as Done"
              │
              ▼
        QuizModal opens
              │
              ├─► POST /chat/sessions/{id}/quiz
              │     └─► LLM generates 3 questions
              │     └─► Answers saved: PostgreSQL chat_messages (role=system)
              │     └─► Questions returned (NO answers)
              │
              ▼
        User answers → clicks "Submit Quiz"
              │
              ├─► POST /chat/sessions/{id}/quiz/submit
              │     └─► PostgreSQL: reads hidden __QUIZ_ANSWERS__ message
              │     └─► Grades answers
              │     └─► If passed: sets quiz_passed=true on user_node_progress
              │
              ▼
        If passed → 1.8s delay → onPassed()
              │
              ├─► POST /progress/.../nodes/{id} { status: "done" }
              │     └─► PostgreSQL: user_node_progress status='done'
              │     └─► Backend: _auto_complete_parents() runs atomically
              │     └─► PostgreSQL: point_transactions (if roadmap complete)
              │
              └─► Frontend re-fetches → React Flow re-renders → green nodes ✅
```

---

## Part 8: Key Files Reference

| Layer | File | Role |
|---|---|---|
| **Graph Library** | `@xyflow/react` (npm) | Renders the interactive node graph |
| **Graph Builder** | `RoadmapDetail.jsx` → `buildGraph()` | Converts flat node list to React Flow format |
| **Custom Node UI** | `RoadmapDetail.jsx` → `RoadmapNode()` | The visual bubble for each roadmap node |
| **API Client** | `src/api/client.js` | All `axios` calls to the FastAPI backend |
| **Quiz Modal** | `RoadmapDetail.jsx` → `QuizModal()` | Renders questions, handles submission |
| **Chat Route** | `app/api/v1/routes/chat.py` | FastAPI endpoints for quiz generate + submit |
| **Progress Route** | `app/api/v1/routes/progress.py` | FastAPI endpoint for marking node done |
| **Chat Service** | `app/services/chat_service.py` | LLM call, answer storage, grading logic |
| **Progress Service** | `app/services/progress_service.py` | Node status update, XP award, parent auto-complete |
| **User Repository** | `app/repositories/user_repository.py` | `add_xp()` — writes to point_transactions |
| **Database** | PostgreSQL | All persistent data |
| **AI Model** | Gemini (configurable) | Generates quiz questions |
