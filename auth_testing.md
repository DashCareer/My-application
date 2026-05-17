# Auth Testing Playbook for DashCareer

This app uses Emergent Google OAuth. Backend session is stored in MongoDB collections `users` and `user_sessions`. The `session_token` cookie (httpOnly, samesite=none, secure) is set on `/api/auth/session`. The same token also works as `Authorization: Bearer <token>`.

## Create a test session via mongo
```bash
mongosh "$MONGO_URL/$DB_NAME" --eval '
var userId = "test-user-" + Date.now();
var token  = "test_session_" + Date.now();
db.users.insertOne({user_id:userId,email:"qa+"+Date.now()+"@dashcareer.test",name:"QA User",picture:"",plan:"free",created_at:new Date().toISOString()});
db.user_sessions.insertOne({user_id:userId,session_token:token,expires_at:new Date(Date.now()+7*86400000).toISOString(),created_at:new Date().toISOString()});
print("TOKEN="+token);
print("USER_ID="+userId);
'
```

## API checks
```bash
API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)
curl -s "$API/api/auth/me" -H "Authorization: Bearer $TOKEN"
curl -s "$API/api/applications" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$API/api/applications" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"company":"Acme","role":"PM"}'
curl -s "$API/api/analytics/overview" -H "Authorization: Bearer $TOKEN"
```

## Browser cookie injection
```javascript
await context.add_cookies([{
  name: "session_token",
  value: "<TOKEN>",
  domain: "<HOSTNAME>",   // host of REACT_APP_BACKEND_URL
  path: "/",
  httpOnly: true,
  secure: true,
  sameSite: "None"
}]);
await page.goto("https://<HOSTNAME>/dashboard");
```

## Cleanup
```bash
mongosh "$MONGO_URL/$DB_NAME" --eval '
db.users.deleteMany({email:/qa\+/});
db.user_sessions.deleteMany({session_token:/test_session/});
'
```
