# Deployment Information

## Public URL
https://k5-l3b-day14-tranquangha-2a202603962-deployment-production.up.railway.app

## Platform
Railway (Root Directory: `06-lab-complete`, Dockerfile multi-stage + Railway Redis)

## Test Commands

### Health & Readiness Checks
```bash
BASE="https://k5-l3b-day14-tranquangha-2a202603962-deployment-production.up.railway.app"

curl -sS "$BASE/health"
# Expected (200): {"status":"ok","environment":"production"}

curl -sS "$BASE/ready"
# Expected (200): {"status":"ready"}
```

### API Test (Authentication)
```bash
# Without API key → 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'

# With API key → 200
curl -sS -X POST "$BASE/ask" \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "What is deployment?"}'
```

## Environment Variables Set
- `PORT` (auto-injected by Railway)
- `ENVIRONMENT` (`production`)
- `REDIS_URL` (`${{Redis.REDIS_URL}}`)
- `AGENT_API_KEY` (set securely on Railway Variables)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
