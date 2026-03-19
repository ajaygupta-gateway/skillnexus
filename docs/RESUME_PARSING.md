# SkillNexus: Resume Parsing & AI Analysis

This document covers the resume upload pipeline, PII sanitization,
AI-powered skill extraction, and the roadmap suggestion workflow.

---

## Overview

The Resume feature allows users to upload a PDF resume. The system:

1. **Extracts** raw text from the PDF
2. **Sanitizes** PII (phone numbers, emails, addresses, profile URLs)
3. **Sends** the sanitized text to an LLM for analysis
4. **Returns** extracted skills, experience years, and suggested roadmap titles
5. **Provides** role-appropriate actions (admin: generate roadmap, learner: request admin)

---

## Architecture

```
User uploads PDF
       │
       ▼
  POST /api/v1/resume/upload (multipart/form-data)
       │
       ▼
  ResumeService.analyze_resume()
       │
       ├─► 1. Validate file (type + size)
       ├─► 2. Save to disk (UPLOAD_DIR)
       ├─► 3. Extract text (pdfminer.six)
       ├─► 4. Sanitize PII (_sanitize_resume_text)
       ├─► 5. Send to LLM (structured output)
       └─► 6. Save result to DB + return
```

---

## 1. PDF Text Extraction

**Library:** `pdfminer.six` (pure Python, no system dependencies)

```python
from pdfminer.high_level import extract_text as pdfminer_extract

def _extract_text_from_pdf(file_path: str) -> str:
    text = pdfminer_extract(file_path)
    return text.strip()
```

**Why pdfminer.six?**
- No system-level dependencies (unlike PyMuPDF which needs `libmupdf`)
- Works in Docker containers without additional OS packages
- Handles most PDF layouts well

---

## 2. PII Sanitization

Before sending resume text to the LLM, all personal identifiable information is removed.
This protects user privacy when text is processed by external AI APIs.

### What Gets Removed

| PII Type | Pattern | Replacement |
|---|---|---|
| **Phone Numbers** | `+91 98765 43210`, `(123) 456-7890`, `1234567890` | `[PHONE REMOVED]` |
| **Emails** | `user@example.com` | `[EMAIL REMOVED]` |
| **LinkedIn URLs** | `linkedin.com/in/username` | `[PROFILE URL REMOVED]` |
| **GitHub URLs** | `github.com/username` | `[PROFILE URL REMOVED]` |
| **Twitter/X URLs** | `twitter.com/user`, `x.com/user` | `[PROFILE URL REMOVED]` |
| **Addresses** | Lines starting with `Address:` or `Location:` | `[ADDRESS REMOVED]` |
| **PIN/ZIP Codes** | 6-digit Indian PIN, 5-digit US ZIP | `[ADDRESS REMOVED]` |

### Phone Number Patterns

The sanitizer handles a wide variety of phone formats:

```
+91 98765 43210      → broad international
+1 (123) 456-7890    → US with country code
(123) 456-7890       → US standard
123-456-7890         → US with dashes
98765 43210          → Indian with space
1234567890           → plain 10-digit
```

### URL Matching

Profile URLs are matched with or without `https://` prefix:

```
https://www.linkedin.com/in/johndoe  → [PROFILE URL REMOVED]
linkedin.com/in/johndoe              → [PROFILE URL REMOVED]
www.github.com/octocat               → [PROFILE URL REMOVED]
github.com/octocat                   → [PROFILE URL REMOVED]
```

### Logging

The sanitizer prints before/after text to Docker container logs for debugging:

```
============================================================
BEFORE SANITIZATION (first 500 chars):
John Doe | +91 98765 43210 | john@gmail.com | linkedin.com/in/johndoe ...
============================================================
AFTER SANITIZATION (first 500 chars):
John Doe | [PHONE REMOVED] | [EMAIL REMOVED] | [PROFILE URL REMOVED] ...
============================================================
PII Sanitization summary — Phones: 1, Emails: 1, URLs: 1, Addresses: 0
```

View logs with: `docker logs skillnexus-api --tail 30`

---

## 3. LLM Analysis

After sanitization, the text is sent to the configured LLM with a structured output schema.

### Prompt

```
You are a professional resume analyzer.
Analyze the following resume text and extract structured information.

Resume Text:
{sanitized_text}
```

### Structured Output Schema

```python
class _ResumeAnalysisSchema(BaseModel):
    extracted_skills: list[str]           # ["Python", "React", "SQL", ...]
    experience_years: float | None         # 3.5
    suggested_roadmap_titles: list[str]    # ["Python Advanced", "System Design"]
```

The LLM is forced to return this exact structure using `get_structured_llm()`,
which uses Pydantic schema validation.

### Response to Frontend

```json
{
  "id": "uuid",
  "extracted_skills": ["Python", "React", "FastAPI", "Docker"],
  "experience_years": 3,
  "suggested_roadmap_titles": ["Advanced Python", "System Design", "Cloud Architecture"],
  "created_at": "2026-03-19T..."
}
```

---

## 4. Frontend — Suggested Roadmap Actions

After analysis, the suggested roadmaps are shown with role-appropriate action buttons:

### For Each Suggested Title:

```
┌─────────────────────────────────────────────────┐
│  Check: Does a roadmap with this title exist?   │
│                                                 │
│  YES → "View & Enroll" button                   │
│         → navigates to /roadmaps/{id}           │
│                                                 │
│  NO → Admin? → "✨ Generate by AI" button        │
│        → POST /roadmaps/generate                │
│        → navigates to new roadmap               │
│                                                 │
│  NO → Learner? → "Request Admin" button         │
│        → POST /roadmaps/request                 │
│        → badge changes to "Requested"           │
└─────────────────────────────────────────────────┘
```

### Matching Logic

The frontend pre-fetches all existing roadmaps on page load:
```js
roadmapApi.list({ page_size: 100 })
```

Then matches by case-insensitive title comparison:
```js
const existing = roadmaps.find(r => r.title.toLowerCase() === t.toLowerCase());
```

---

## 5. Resume History

Users can view past resume analyses:

```
GET /api/v1/resume/me
→ Returns list of previous uploads with extracted data
```

---

## 6. Configuration

| Setting | Description |
|---|---|
| `MAX_FILE_SIZE_MB` | Maximum upload size (default: 10MB) |
| `UPLOAD_DIR` | Directory for saved PDFs |
| LLM API Key | `GROQ_API_KEY` or `GEMINI_API_KEY` in `.env` |

---

## 7. Key Files

| File | Role |
|---|---|
| `backend/app/api/v1/routes/resume.py` | Upload endpoint |
| `backend/app/services/resume_service.py` | Full pipeline: extract → sanitize → LLM → save |
| `backend/app/core/llm.py` | LLM client setup (structured output) |
| `frontend/.../pages/Resume.jsx` | Upload UI, skill tags, suggested roadmaps |
| `frontend/.../api/client.js` | `resumeApi.upload()` + `roadmapApi.generate()` |

---

## 8. Error Handling

| Error | HTTP Code | Cause |
|---|---|---|
| `Invalid file type` | 422 | Non-PDF file uploaded |
| `File size exceeds maximum` | 413 | File > `MAX_FILE_SIZE_MB` |
| `Failed to extract text` | 400 | Corrupted or encrypted PDF |
| `AI service temporarily unavailable` | 503 | LLM API down or rate limited |
