# DashCareer Test Credentials

## Authentication
This app uses **Emergent-managed Google OAuth** (no app-managed passwords).

### Test Identity
- Any valid Google account can sign in via the "Continue with Google" button on `/login`.
- The OAuth redirect lands at `${origin}/dashboard#session_id=...` and is processed by `/api/auth/session`.

### Manual session creation (for testing agent)
```bash
mongosh "$MONGO_URL/$DB_NAME" --eval '
var userId = "test-user-" + Date.now();
var token  = "test_session_" + Date.now();
db.users.insertOne({user_id:userId,email:"test.user."+Date.now()+"@example.com",name:"Test User",picture:"",plan:"free",created_at:new Date().toISOString()});
db.user_sessions.insertOne({user_id:userId,session_token:token,expires_at:new Date(Date.now()+7*86400000).toISOString(),created_at:new Date().toISOString()});
print("TOKEN="+token);
print("USER_ID="+userId);
'
```

Then send requests with cookie `session_token=<TOKEN>` or header `Authorization: Bearer <TOKEN>`.

## Plans / RBAC
- `plan: "free"` — limited to 10 applications, 5 AI requests/day
- `plan: "pro"` — unlimited
