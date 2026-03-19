# SkillNexus: Authentication & JWT Flow

This document covers the complete authentication system — JWT creation, payload structure,
token lifecycle, storage, refresh mechanism, revocation, and usage across backend and frontend.

---

## 1. Overview

SkillNexus uses a **dual-token JWT strategy**:

| Token | Purpose | Lifetime | Stored In | Revocable |
|---|---|---|---|---|
| **Access Token** | Authenticate API requests | 1440 min (24h) | Client `localStorage` only | ❌ No (stateless) |
| **Refresh Token** | Get new access tokens | 30 days | Client `localStorage` + SHA-256 hash in DB | ✅ Yes |

**Library:** `python-jose` (backend JWT encode/decode), `bcrypt` (password hashing)  
**Algorithm:** `HS256` (HMAC-SHA256)

---

## 2. JWT Payload Structure

### Access Token Payload

Created in `security.py` → `create_access_token()`:

```python
token_data = {"sub": str(user.id), "email": user.email, "role": user.role}
```

After encoding, the full JWT payload looks like:

```json
{
  "sub": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "email": "user@example.com",
  "role": "learner",
  "exp": 1710900000,
  "type": "access"
}
```

| Field | Type | Source | Purpose |
|---|---|---|---|
| `sub` | string (UUID) | `user.id` | Identifies the user — used by `get_current_user()` to load user from DB |
| `email` | string | `user.email` | Informational (not used for auth decisions) |
| `role` | string | `user.role` | Informational, not used server-side (role is always re-read from DB) |
| `exp` | int (Unix timestamp) | `datetime.now(UTC) + timedelta(minutes=1440)` | Token expiration — `python-jose` auto-rejects expired tokens |
| `type` | string | hardcoded `"access"` | Prevents using a refresh token as an access token |

**Signing key:** `JWT_SECRET_KEY` (from `.env`, minimum 32 characters)

### Refresh Token Payload

Created in `security.py` → `create_refresh_token()`:

```json
{
  "sub": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "email": "user@example.com",
  "role": "learner",
  "exp": 1713492000,
  "type": "refresh",
  "jti": "xK9mPqR7vLwT3nYz..."
}
```

| Field | Type | Purpose |
|---|---|---|
| `sub`, `email`, `role` | Same as access | Same user data |
| `exp` | Unix timestamp | 30 days from creation |
| `type` | `"refresh"` | Prevents using as access token |
| `jti` | string (44 chars) | **JWT ID** — unique random value via `secrets.token_urlsafe(32)`. Ensures each refresh token is unique even for the same user |

**Signing key:** `JWT_REFRESH_SECRET_KEY` (separate from access token key!)

---

## 3. Token Creation (Login Flow)

### Step-by-step: What happens when a user logs in

```
Frontend:
  POST /api/v1/auth/login
  Body: { "email": "user@example.com", "password": "secret123" }
```

**Backend (`auth_service.py` → `login()`):**

```
1. Fetch user by email from DB
2. Verify password: bcrypt.checkpw(plain, hashed)
   → If wrong → 401 "Invalid email or password"

3. Update streak + daily login XP:
   → update_streak(user) checks if first login today
   → If first login: +5 XP (login bonus)
   → If 7-day streak: +30 XP (streak bonus)

4. Update level: total_xp // 500 + 1

5. Build token_data:
   token_data = {
     "sub": "uuid-string",
     "email": "user@example.com",
     "role": "learner"
   }

6. Create access token:
   → Adds: { "exp": now + 1440min, "type": "access" }
   → Signs with JWT_SECRET_KEY using HS256
   → Returns: "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOi..."

7. Create refresh token:
   → Adds: { "exp": now + 30days, "type": "refresh", "jti": random_44_chars }
   → Signs with JWT_REFRESH_SECRET_KEY using HS256

8. Store refresh token hash in DB:
   → hash_token(refresh_token) → SHA-256 hex digest (64 chars)
   → Saves to `refresh_tokens` table:
     { user_id, token_hash, expires_at, revoked: false }

9. Return to frontend:
   { "access_token": "eyJ...", "refresh_token": "eyJ..." }
```

**Frontend (`AuthContext.jsx` → `login()`):**

```javascript
const { data } = await authApi.login({ email, password });
localStorage.setItem('access_token', data.access_token);  // stored here
localStorage.setItem('refresh_token', data.refresh_token); // stored here
await loadUser();  // calls GET /users/me to populate user state
```

---

## 4. Token Usage (Every API Request)

### Frontend: Auto-attaching the access token

In `client.js`, an **Axios request interceptor** runs before every API call:

```javascript
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
```

This adds the header:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOi...
```

### Backend: Validating the access token

The `get_current_user()` dependency in `deps.py` runs for every protected route:

```
1. Extract token from "Authorization: Bearer <token>" header
   → Uses FastAPI's HTTPBearer scheme

2. Decode + validate:
   payload = decode_access_token(token)
   → python-jose decodes with JWT_SECRET_KEY
   → Automatically rejects: expired tokens, tampered tokens, wrong algorithm
   → Manually checks: payload["type"] == "access"

3. Extract user ID:
   user_id = payload["sub"]  // "a1b2c3d4-..."

4. Load user from DB:
   user = await UserRepository.get_by_id(UUID(user_id))
   → If user not found → 401
   → If user.is_active == False → 401

5. Return the User ORM object to the route handler
```

### Role-Based Access Control

The `require_roles()` dependency factory adds an extra check:

```python
# Convenience types used in route signatures:
CurrentUser = Annotated[User, Depends(get_current_user)]          # any authenticated user
AdminUser = Annotated[User, Depends(require_roles(UserRole.admin))]     # admin only
AdminOrManager = Annotated[User, Depends(require_roles(admin, manager))] # admin or manager

# Usage in a route:
@router.post("/assignments")
async def create_assignments(current_user: AdminUser, db: DB):
    # Only reaches here if user.role == "admin"
    # Otherwise → 403 "Required roles: ['admin']. Your role: learner"
```

**Important:** The role from the JWT payload is NOT used for authorization.
The role is always re-read from the DB via `get_current_user()`. This means
if an admin demotes a user, the change takes effect immediately (no need to
wait for token expiry).

---

## 5. Token Refresh Flow

When the access token expires, the frontend automatically refreshes it:

### Frontend: Automatic refresh (Axios response interceptor)

```javascript
api.interceptors.response.use(
  (res) => res,  // success → pass through
  async (err) => {
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true;  // prevent infinite loop
      const refresh = localStorage.getItem('refresh_token');
      
      // Try to get a new access token
      const { data } = await axios.post('/auth/refresh', { refresh_token: refresh });
      localStorage.setItem('access_token', data.access_token);
      
      // Retry the original failed request with new token
      original.headers.Authorization = `Bearer ${data.access_token}`;
      return api(original);
    }
    // If refresh also fails → clear storage, redirect to /login
  }
);
```

### Backend: Refresh endpoint (`auth_service.py` → `refresh_access_token()`)

```
POST /api/v1/auth/refresh
Body: { "refresh_token": "eyJ..." }

1. Decode refresh token:
   → Uses JWT_REFRESH_SECRET_KEY (different from access key!)
   → Checks type == "refresh"
   → Checks expiration

2. Verify in DB:
   → SHA-256 hash the refresh token
   → Look up hash in refresh_tokens table
   → Check: exists? not revoked? not expired?

3. Rotate tokens:
   → REVOKE the old refresh token (set revoked=true)
   → Generate NEW access token
   → Generate NEW refresh token (with new jti)
   → Store new refresh token hash in DB

4. Return:
   { "access_token": "eyJ...new..." }
```

**Token Rotation Security:** Each refresh token can only be used ONCE.
After use, it's revoked and a new one is issued. If an attacker steals
a refresh token and tries to use it after the legitimate user has already
refreshed, the stolen token will fail (already revoked).

---

## 6. Logout & Token Revocation

### Single Device Logout

```
POST /api/v1/auth/logout
Body: { "refresh_token": "eyJ..." }

Backend:
  1. Hash the refresh token
  2. Find it in DB
  3. Set revoked = true
  → Idempotent: no error if token not found
```

### All Devices Logout

```
POST /api/v1/auth/logout-all
Requires: valid access token (Authorization header)

Backend:
  → Revokes ALL refresh tokens for the user
  → User must re-login on every device
```

### Frontend Logout

```javascript
const logout = async () => {
    const rt = localStorage.getItem('refresh_token');
    try { await authApi.logout(rt); } catch { /* ignore */ }
    localStorage.clear();    // remove both tokens
    setUser(null);           // clear user state
};
```

---

## 7. Password Security

| Aspect | Implementation |
|---|---|
| **Hashing** | `bcrypt` with 12 salt rounds |
| **Storage** | Only `hashed_password` is stored in DB (never plaintext) |
| **Verification** | `bcrypt.checkpw(plain, hashed)` — constant-time comparison |

```python
# Registration
hashed_pw = hash_password(data.password)
# → "$2b$12$LJ3m4K..." (bcrypt hash with salt embedded)

# Login
verify_password("user_input", stored_hash)
# → True or False
```

---

## 8. Configuration (from `.env`)

| Setting | Default | Description |
|---|---|---|
| `JWT_SECRET_KEY` | *(required, min 32 chars)* | Signs access tokens |
| `JWT_REFRESH_SECRET_KEY` | *(required, min 32 chars)* | Signs refresh tokens (separate key!) |
| `JWT_ALGORITHM` | `HS256` | HMAC-SHA256 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24 hours) | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token lifetime |

**Generate secret keys:**
```bash
openssl rand -hex 32
# or
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 9. Database: `refresh_tokens` Table

```
refresh_tokens
├── id           UUID (PK)
├── user_id      UUID (FK → users.id, CASCADE on delete)
├── token_hash   String(64), unique, indexed  ← SHA-256 of the JWT
├── expires_at   DateTime (timezone-aware)
├── revoked      Boolean (default: false)
└── created_at   DateTime (server_default: now())
```

**Why store hash, not the raw token?**
If the DB is breached, attackers get hashes, not usable tokens.
SHA-256 is one-way — you can't reverse a hash back to the JWT.

---

## 10. Complete Auth Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        REGISTRATION                         │
│                                                             │
│  POST /auth/register { email, password, display_name }      │
│    → bcrypt.hash(password)                                  │
│    → Save user to DB                                        │
│    → Auto-login (calls login flow below)                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                          LOGIN                              │
│                                                             │
│  POST /auth/login { email, password }                       │
│    → Verify: bcrypt.checkpw(password, stored_hash)          │
│    → Update streak + award daily XP (if first login today)  │
│    → Build: { sub: user_id, email, role }                   │
│    → Sign access_token  (JWT_SECRET_KEY, exp: 24h)          │
│    → Sign refresh_token (JWT_REFRESH_SECRET_KEY, exp: 30d)  │
│    → Store SHA-256(refresh_token) in DB                     │
│    → Return: { access_token, refresh_token }                │
│                                                             │
│  Frontend:                                                  │
│    → localStorage.set('access_token', ...)                  │
│    → localStorage.set('refresh_token', ...)                 │
│    → GET /users/me → populate user state                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     EVERY API REQUEST                       │
│                                                             │
│  Axios interceptor:                                         │
│    → Reads access_token from localStorage                   │
│    → Adds header: Authorization: Bearer <token>             │
│                                                             │
│  Backend dependency (get_current_user):                     │
│    → Decode JWT with JWT_SECRET_KEY                         │
│    → Extract user_id from payload["sub"]                    │
│    → Load user from DB (fresh role, XP, etc.)               │
│    → Return User object to route handler                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     TOKEN REFRESH                           │
│                                                             │
│  When any API returns 401:                                  │
│    → Axios interceptor catches it                           │
│    → POST /auth/refresh { refresh_token }                   │
│    → Backend: verify hash in DB, check not revoked          │
│    → Revoke old refresh token                               │
│    → Issue new access_token + new refresh_token             │
│    → Store new refresh hash in DB                           │
│    → Return new access_token to frontend                    │
│    → Retry the original failed request                      │
│                                                             │
│  If refresh also fails:                                     │
│    → localStorage.clear()                                   │
│    → Redirect to /login                                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                         LOGOUT                              │
│                                                             │
│  POST /auth/logout { refresh_token }                        │
│    → Backend: set revoked=true on DB record                 │
│    → Frontend: localStorage.clear() + setUser(null)         │
│                                                             │
│  POST /auth/logout-all (requires access token)              │
│    → Backend: revoke ALL refresh tokens for user            │
└─────────────────────────────────────────────────────────────┘
```

---

## 11. Security Summary

| Threat | Protection |
|---|---|
| **Token tampering** | HS256 signature — any modification invalidates the token |
| **Token expiry** | Access: 24h, Refresh: 30d — `exp` claim auto-checked by `python-jose` |
| **Token type confusion** | `type` field prevents using refresh token as access token (and vice versa) |
| **Stolen refresh token** | Token rotation — each refresh token works only once |
| **DB breach** | Refresh tokens stored as SHA-256 hashes, not raw JWTs |
| **Password breach** | Passwords stored as bcrypt hashes (12 rounds, salt embedded) |
| **Role escalation** | Role from JWT is ignored — role is always re-read from DB |
| **Session hijacking** | Logout-all revokes every refresh token across all devices |
| **XSS token theft** | Tokens in `localStorage` (trade-off: vulnerable to XSS but simple to implement) |

---

## 12. Key Files

| File | Role |
|---|---|
| `backend/app/core/security.py` | JWT encode/decode, bcrypt hash/verify, token hashing |
| `backend/app/core/config.py` | JWT settings (keys, algorithm, lifetimes) |
| `backend/app/api/deps.py` | `get_current_user()` dependency — decodes JWT + loads user |
| `backend/app/api/v1/routes/auth.py` | Login, register, refresh, logout routes |
| `backend/app/services/auth_service.py` | Auth business logic (token creation, rotation, revocation) |
| `backend/app/models/models.py` | `RefreshToken` model (DB schema) |
| `frontend/.../context/AuthContext.jsx` | Login/logout state, `loadUser()`, token storage |
| `frontend/.../api/client.js` | Axios interceptors (auto-attach, auto-refresh) |
