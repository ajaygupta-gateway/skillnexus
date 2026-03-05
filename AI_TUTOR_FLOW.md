# AI Tutor Flow (Start to End)

This document explains how the AI Tutor works for each roadmap node, including chat history, LLM response generation, quiz generation, and quiz submission.

## 1. Frontend opens AI Tutor for a node

- File: `frontend/skill-nexus/src/pages/RoadmapDetail.jsx`
- Component: `ChatPanel({ node })`
- When user selects the **AI Tutor** tab for a node:
  - `chatApi.getMessages(node.id, node.roadmap_id)` is called.
  - Existing conversation for that user+node is loaded.

API helper:
- File: `frontend/skill-nexus/src/api/client.js`
- `getMessages: (nid, rid) => api.get('/chat/sessions/{nid}/messages', { params: { roadmap_id: rid } })`

## 2. Backend returns/create session + history

- Route: `GET /api/v1/chat/sessions/{node_id}/messages`
- File: `backend/app/api/v1/routes/chat.py`
- Calls `ChatService.get_chat_history(...)`.

In service:
- File: `backend/app/services/chat_service.py`
- Validates node exists.
- Gets or creates a session for `(user_id, node_id)` via repository.
- Fetches stored messages in chronological order.
- Returns `ChatHistoryResponse`.

Session behavior:
- File: `backend/app/repositories/chat_repository.py`
- `get_or_create_session()` enforces one session per `(user_id, node_id)`.
- DB uniqueness constraint:
  - File: `backend/app/models/models.py`
  - `UniqueConstraint("user_id", "node_id", name="uq_chat_session_user_node")`

## 3. User sends a message

Frontend:
- `chatApi.sendMessage(node.id, node.roadmap_id, { content: text })`
- Route used: `POST /api/v1/chat/sessions/{node_id}/messages?roadmap_id=...`

Backend:
- File: `backend/app/api/v1/routes/chat.py`
- Calls `ChatService.send_message(...)`.

## 4. How AI response is generated

In `ChatService.send_message(...)`:

1. Validate node exists and load roadmap title.
2. Get/create chat session.
3. Persist user message to `chat_messages` with role `user`.
4. Build system prompt scoped to current node/roadmap:
   - "You are an expert corporate trainer..."
   - Keep answers focused on node topic.
5. Load last 20 messages for context.
6. Convert DB messages to LangChain messages:
   - `HumanMessage` for user role
   - `AIMessage` for assistant role
7. Call LLM using `get_llm().ainvoke(lc_messages)`.
8. Persist assistant response to DB with role `assistant`.
9. Return assistant message payload to frontend.

LLM provider selection:
- File: `backend/app/services/llm_factory.py`
- Fallback order: `gemini -> groq -> openai`

## 5. Frontend renders AI response

- File: `frontend/skill-nexus/src/pages/RoadmapDetail.jsx`
- Assistant messages are rendered using `ReactMarkdown` + `remarkGfm`.
- User sees formatted lists/code/links in chat bubbles.

## 6. Quiz generation flow

Frontend:
- When learner clicks "Mark as Done", quiz modal opens.
- It calls: `chatApi.generateQuiz(node.id, node.roadmap_id)`.

Backend:
- Route: `POST /api/v1/chat/sessions/{node_id}/quiz`
- Service: `ChatService.generate_quiz(...)`

What happens:
1. Build quiz prompt from node title + description.
2. Call structured LLM with `_QuizSchema`:
   - Exactly 3 questions
   - Each question has 4 options (A-D)
   - Includes correct answer key
3. Store correct answers as hidden system message in same session:
   - Prefix format: `__QUIZ_ANSWERS__:{...json...}`
4. Return only question text/options to frontend (not answers).

## 7. Quiz submission flow

Frontend:
- Calls `chatApi.submitQuiz(node.id, node.roadmap_id, { answers })`
- `answers` format: `{ "1": "A", "2": "C", "3": "B" }`

Backend:
- Route: `POST /api/v1/chat/sessions/{node_id}/quiz/submit`
- Service: `ChatService.submit_quiz(...)`

What happens:
1. Load latest hidden `__QUIZ_ANSWERS__` system message.
2. Compare submitted answers (case-insensitive).
3. Compute score and pass/fail.
4. Pass condition: `score >= 2` out of 3.
5. If passed:
   - mark `quiz_passed=True` on node progress
   - award 25 XP (event `quiz_pass`)
6. Return `QuizResult` with:
   - score, passed, threshold
   - `quiz_now_passed`
   - `can_mark_done`
   - feedback

## 8. Progress unlock connection

Quiz result is consumed by learner flow:
- If quiz passed, frontend marks current node done and unlocks next node.
- Backend strict-mode rules also check `quiz_passed` before allowing done in strict assignments.
- Related file: `backend/app/services/progress_service.py`

## 9. Transaction behavior

- Session dependency commits on successful request:
  - File: `backend/app/core/database.py`
  - `await session.commit()` after route completion
- Repositories use `flush()` during request for immediate IDs/visibility, but final persistence is at commit.

---

## Detailed Example (Step-by-step)

### Scenario

- User: `u_001`
- Roadmap: `React Mastery` (`roadmap_id = rm_101`)
- Node: `Hooks Deep Dive` (`node_id = n_501`)

### Step A: User opens AI Tutor tab

Frontend request:

```http
GET /api/v1/chat/sessions/n_501/messages?roadmap_id=rm_101
Authorization: Bearer <token>
```

Backend behavior:
- Finds/creates session `(u_001, n_501)`, e.g. `session_id = s_9001`
- Returns existing messages (if any).

Example response:

```json
{
  "session": {
    "id": "s_9001",
    "user_id": "u_001",
    "node_id": "n_501",
    "roadmap_id": "rm_101",
    "node_title": "Hooks Deep Dive",
    "message_count": 2
  },
  "messages": [
    { "role": "user", "content": "What is stale closure in useEffect?" },
    { "role": "assistant", "content": "A stale closure happens when..." }
  ]
}
```

### Step B: User asks a new question

Frontend request:

```http
POST /api/v1/chat/sessions/n_501/messages?roadmap_id=rm_101
Authorization: Bearer <token>
Content-Type: application/json

{
  "content": "How do I avoid unnecessary re-renders with hooks?"
}
```

Backend processing:
1. Save user message to `chat_messages`.
2. Build system prompt tied to `"Hooks Deep Dive"` + `"React Mastery"`.
3. Load last 20 messages for context.
4. Call LLM.
5. Save assistant message.

Example assistant response returned:

```json
{
  "id": "m_3003",
  "session_id": "s_9001",
  "role": "assistant",
  "content": "Use memoization carefully: `React.memo`, `useMemo`, and `useCallback`..."
}
```

### Step C: User starts quiz for this node

Frontend request:

```http
POST /api/v1/chat/sessions/n_501/quiz?roadmap_id=rm_101
Authorization: Bearer <token>
```

Backend:
- Structured LLM generates 3 MCQs.
- Correct answers stored as hidden system message:

```text
__QUIZ_ANSWERS__:{"1":"B","2":"A","3":"D"}
```

Frontend-visible response:

```json
{
  "node_id": "n_501",
  "node_title": "Hooks Deep Dive",
  "total_questions": 3,
  "questions": [
    {
      "question_number": 1,
      "question": "Which hook memoizes a computed value?",
      "options": [
        { "key": "A", "text": "useEffect" },
        { "key": "B", "text": "useMemo" },
        { "key": "C", "text": "useState" },
        { "key": "D", "text": "useRef" }
      ]
    }
  ]
}
```

### Step D: User submits quiz answers

Frontend request:

```http
POST /api/v1/chat/sessions/n_501/quiz/submit?roadmap_id=rm_101
Authorization: Bearer <token>
Content-Type: application/json

{
  "answers": {
    "1": "B",
    "2": "A",
    "3": "C"
  }
}
```

Backend grading:
- Correct: Q1, Q2
- Wrong: Q3
- Score = 2/3 => pass
- Sets `quiz_passed = true` in `user_node_progress`
- Awards +25 XP

Example result:

```json
{
  "score": 2,
  "total": 3,
  "passed": true,
  "pass_threshold": 2,
  "node_id": "n_501",
  "quiz_now_passed": true,
  "can_mark_done": true,
  "feedback": "🎉 Excellent! You scored 2/3..."
}
```

### Step E: Node unlock flow continues

- Frontend then marks current node done via progress API.
- Next node can be moved to `in_progress`.
- Learner sees progress/XP updates in UI.
