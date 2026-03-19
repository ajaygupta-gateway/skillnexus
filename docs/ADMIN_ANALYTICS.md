# SkillNexus: Admin Analytics & Control Center

This document covers the admin-facing features: the Control Center (admin panel),
assignment management, analytics dashboard, skill gap analysis, user-level reports,
and roadmap request handling.

---

## Overview

Admin users (`role: admin`) and managers (`role: manager`) access the **Control Center**
from the sidebar navigation. The Control Center provides:

1. **Platform Statistics** — high-level metrics
2. **Assignment Management** — assign/unassign roadmaps to learners
3. **Roadmap Requests** — review and fulfill learner-requested roadmaps
4. **User Analytics** — per-learner progress reports

---

## 1. Dashboard (Home Page for Admins)

The Dashboard (`/`) renders a completely different view for admins vs learners:

### Admin Dashboard Shows:
| Widget | Data Source | Details |
|---|---|---|
| **Total Users** | `GET /admin/analytics/dashboard` | Count of all active users |
| **Total Roadmaps** | Same endpoint | All non-deleted roadmaps |
| **Active Assignments** | Same endpoint | Total assignment count |
| **Avg Completion** | Same endpoint | Average `completion_percentage` across all assignments |
| **Quick Actions** | Frontend buttons | Navigate to Roadmaps, Control Center, Resume Analysis |
| **Recent Assignments** | `GET /admin/assignments?page_size=5` | Last 5 assigned roadmaps with progress bars |
| **Pending Requests** | `GET /admin/roadmap-requests` | Roadmap requests from learners with `status: pending` |

### Learner Dashboard Shows:
| Widget | Data |
|---|---|
| Total XP | From `user.xp_balance` |
| Level | From `user.level` |
| Day Streak | From `user.streak_count` |
| XP Progress Bar | XP to next level (500 XP per level) |
| Weekly Leaderboard | `GET /users/leaderboard` |
| Recent XP Events | `GET /users/me/transactions` |

---

## 2. Control Center (`/admin`)

The Control Center page has three tabs:

### Tab 1: Assignments

Shows a table of all roadmap assignments with:
- User display name and email
- Roadmap title
- Assignment status (`active` / `completed` / `archived`)
- Completion percentage with progress bar
- Last active timestamp
- Actions: **Remove** assignment (admin only, not managers)

**Assign Roadmap Flow:**
```
Admin clicks "Assign" button
  ↓
AssignModal opens:
  1. Select a Roadmap (dropdown of all roadmaps)
  2. Select Users (checkbox list of all learners)
  3. Click "Assign"
  ↓
POST /api/v1/admin/assignments
  Body: { user_ids: [...], roadmap_id: "..." }
  ↓
Backend:
  - Creates UserRoadmapAssignment for each selected user
  - strict_mode = true (default, all assignments require quiz)
  - Initializes first root node as 'in_progress' for each user
  ↓
Learner sees roadmap as enrolled with first node ready
```

> **Note:** Strict mode checkbox was removed from the UI. All assignments
> enforce quiz completion by default (`strict_mode: true`).

**Remove Assignment Flow:**
```
Admin clicks "Remove" on an assignment
  ↓
DELETE /api/v1/admin/assignments/{id}
  ↓
Backend:
  1. Deletes ALL UserNodeProgress records for user + roadmap
  2. Deletes the UserRoadmapAssignment record
  ↓
Learner is fully unenrolled (clean slate)
```

### Tab 2: Requests

Shows roadmap requests submitted by learners (from the Resume page or elsewhere):
- Request title
- Requesting user
- Status badge (`pending` / `fulfilled` / `rejected`)
- "Fulfill" and "Reject" action buttons

**Request Fulfillment Flow:**
```
Learner uploads resume → AI suggests roadmaps → "Request Admin" button
  ↓
POST /api/v1/roadmaps/request
  Body: { title: "Data Engineering" }
  ↓
Admin sees request in "Requests" tab
  ↓
Admin clicks "Fulfill" → manually creates or generates the roadmap
  ↓
PATCH /api/v1/admin/roadmap-requests/{id}
  Body: { status: "fulfilled" }
```

### Tab 3: User Analytics

Select a user from the dropdown to view their full learning report:
- XP balance, level, streak count
- All assigned roadmaps with completion percentage
- Per-roadmap status and last activity date

**API:** `GET /api/v1/admin/analytics/users/{user_id}`

---

## 3. Analytics API Endpoints

### Dashboard Stats
```
GET /api/v1/admin/analytics/dashboard

Response:
{
  "total_learners": 42,
  "total_roadmaps": 8,
  "total_assignments": 156,
  "active_this_week": 28,
  "roadmap_summaries": [
    {
      "roadmap_id": "...",
      "roadmap_title": "Python Fundamentals",
      "total_assigned": 35,
      "completed": 12,
      "in_progress": 23,
      "average_completion": 67.50,
      "last_activity": "2026-03-18T..."
    }
  ]
}
```

### Skill Gap Analysis
```
GET /api/v1/admin/analytics/skill-gaps?roadmap_id={id}

Shows per-node breakdown:
  - How many assigned users haven't started each node
  - How many are in progress
  - How many have completed it

Response:
[
  {
    "node_id": "...",
    "node_title": "TypeScript Generics",
    "total_assigned": 20,
    "not_started": 12,
    "in_progress": 5,
    "completed": 3,
    "not_started_percentage": 60.0
  }
]

Use case: "60% of assigned users haven't started TypeScript Generics"
```

### User-Level Report
```
GET /api/v1/admin/analytics/users/{user_id}

Response:
{
  "user_id": "...",
  "display_name": "Jane Doe",
  "email": "jane@company.com",
  "xp_balance": 850,
  "level": 2,
  "streak_count": 5,
  "assignments": [
    {
      "assigned_roadmap": "Python Fundamentals",
      "completion_percentage": 87.5,
      "status": "active",
      "last_active_at": "2026-03-18T...",
      "assigned_at": "2026-03-10T..."
    }
  ]
}
```

---

## 4. Role-Based Access Control

| Feature | Admin | Manager | Learner |
|---|---|---|---|
| View Dashboard (admin view) | ✅ | ✅ | ❌ (sees learner view) |
| Assign roadmaps | ✅ | ❌ | ❌ |
| Remove assignments | ✅ | ❌ | ❌ |
| View assignments table | ✅ | ✅ (read-only) | ❌ |
| View roadmap requests | ✅ | ✅ | ❌ |
| Fulfill/reject requests | ✅ | ✅ | ❌ |
| View analytics | ✅ | ✅ | ❌ |
| Create roadmaps | ✅ | ❌ | ❌ |
| Publish roadmaps | ✅ | ❌ | ❌ |
| Generate roadmaps by AI | ✅ | ❌ | ❌ |
| Enroll in roadmaps | ❌ | ❌ | ✅ |
| View XP/Level/Streak | ❌ | ❌ | ✅ |

---

## 5. UI Differences by Role

### Sidebar
- **Admin/Manager:** Shows `admin` or `manager` badge (no XP/Level)
- **Learner:** Shows `Level X · Y XP`

### Profile Page
- **Admin/Manager:** Only "Display Name" edit field
- **Learner:** XP progress bar, Streak/XP/Level stats, "Display Name" + "Current Role Title" fields

### Resume Page
- **Admin:** Suggested roadmaps show **"✨ Generate by AI"** button (auto-generates the roadmap)
- **Learner:** Suggested roadmaps show **"Request Admin"** button (submits request for admin review)

---

## 6. Key Files

| File | Role |
|---|---|
| `frontend/.../pages/Dashboard.jsx` | Admin: stats + actions. Learner: XP + leaderboard |
| `frontend/.../pages/AdminPanel.jsx` | Control Center: assignments, requests, user analytics tabs |
| `frontend/.../components/Layout.jsx` | Sidebar with role-based user card |
| `frontend/.../pages/Profile.jsx` | Role-aware profile page |
| `frontend/.../pages/Resume.jsx` | Role-aware suggested roadmap actions |
| `backend/app/api/v1/routes/admin.py` | Admin API routes |
| `backend/app/services/progress_service.py` | Assignment CRUD + node initialization + cleanup |
| `backend/app/schemas/progress.py` | Assignment request/response schemas |
