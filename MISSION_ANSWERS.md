# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (`01-localhost-vs-production/develop/app.py`)

1. **Hardcode secrets trong mã nguồn (dòng 17–18):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"`
   - `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`
   - *Rủi ro:* Khi push code lên Git/GitHub, secret bị lộ ngay lập tức (kể cả khi xóa ở commit sau vẫn còn trong lịch sử Git).
2. **Không có cơ chế quản lý cấu hình theo môi trường (dòng 21–22):**
   - `DEBUG = True`, `MAX_TOKENS = 500` viết cứng trong code thay vì đọc từ biến môi trường. Muốn đổi cấu hình giữa dev/staging/production phải sửa code.
3. **Dùng `print()` thay cho structured logging và in secret ra log (dòng 33–38):**
   - Dòng 34: `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm rò rỉ API key trực tiếp ra stdout/log.
   - Log dạng plain text khó parse, lọc và truy vấn tự động trên các hệ thống tập trung (Loki, Datadog).
4. **Thiếu endpoint health check & readiness (dòng 42–43):**
   - Không có `GET /health` và `GET /ready`, nên cloud platform / load balancer không kiểm tra được app còn sống hay đã sẵn sàng nhận traffic để tự động restart hoặc ngắt route.
5. **Bind cứng `host="localhost"` (dòng 51):**
   - `uvicorn.run("app:app", host="localhost", ...)` chỉ lắng nghe loopback nội bộ; khi đóng gói vào Docker container sẽ không thể truy cập từ bên ngoài container (cần `0.0.0.0`).
6. **Hardcode `port=8000` và bật `reload=True` (dòng 52–53):**
   - Không đọc biến `PORT` do nền tảng cloud (Railway/Render) cấp động.
   - `reload=True` dùng cho dev local; bật trên production gây tốn tài nguyên và rủi ro khởi động lại ngoài ý muốn.
7. **Không xử lý Graceful Shutdown & thiếu kiểm soát input (dòng 31, 49–54):**
   - Không có `lifespan` hay xử lý `SIGTERM`, nên khi container dừng sẽ cắt ngang request đang xử lý.
   - Tham số `question: str` nhận qua query string không giới hạn độ dài hoặc validate bằng Pydantic schema.

### Exercise 1.2: Kết quả chạy bản `develop`

Lệnh chạy server (`01-localhost-vs-production/develop/app.py`) và test endpoint (nhận `question` qua query parameter):

```bash
curl -X POST "http://localhost:8000/ask?question=Hello"
```

Kết quả thực tế:

```json
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 1.3: So sánh bản `develop` và `production`

Kết quả test bản `production` (`01-localhost-vs-production/production/app.py`):

```bash
curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
# {"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}

curl http://localhost:8000/health
# {"status":"ok","uptime_seconds":79.1,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:52:52.584084+00:00"}

curl http://localhost:8000/ready
# {"ready":true}
```

Bảng so sánh:

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`, `config.py`) | Why Important? |
| --- | --- | --- | --- |
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG`, `MAX_TOKENS` trong code (dòng 17–22) | `Settings` dataclass đọc qua `os.getenv(...)`, có `.env.example` và `validate()` fail-fast khi `ENVIRONMENT=production` (`config.py` dòng 15–50) | Tách biệt config khỏi code (12-Factor III), tránh lộ secret trên Git và dễ đổi cấu hình theo từng môi trường. |
| **Network Binding & Port** | `host="localhost"`, `port=8000`, `reload=True` (dòng 51–53) | `host=settings.host` (`0.0.0.0`), `port=settings.port` (từ `PORT`), `reload=settings.debug` (dòng 195–198) | `0.0.0.0` cho phép nhận traffic từ ngoài container; đọc `PORT` động giúp chạy được trên Railway/Render; tắt `reload` ở prod để ổn định. |
| **Health & Readiness** | Không có endpoint kiểm tra sức khỏe (dòng 42–43) | Có `GET /health` (liveness, dòng 135–149) và `GET /ready` (readiness trả `503` nếu `not is_ready`, dòng 152–161) | Cloud platform dùng `/health` để restart container khi treo, và load balancer dùng `/ready` để chỉ gửi traffic khi app sẵn sàng. |
| **Logging** | Dùng `print()` plain text và in cả `OPENAI_API_KEY` (dòng 33–38) | Dùng `logging` định dạng JSON với `json.dumps(...)`, chỉ log metadata như `question_length`, `client_ip` (dòng 28–31, 111–122) | Structured JSON log dễ tìm kiếm, lọc và cảnh báo trên log aggregator; không làm rò rỉ thông tin nhạy cảm. |
| **Shutdown** | Tắt đột ngột khi nhận signal | Có `lifespan` context manager đặt `is_ready = False` rồi chờ request hoàn thành, kèm `signal.SIGTERM` handler (dòng 39–67, 180–189) | Đảm bảo graceful shutdown, không làm đứt gãy request của người dùng đang xử lý khi redeploy hoặc scale down. |

**Ví dụ anti-pattern cụ thể đã được sửa:**
- Ở `develop/app.py` (dòng 17 & 34): hardcode `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và log thẳng `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`.
- Ở `production/config.py` (dòng 27, 32, 37–46) & `production/app.py` (dòng 111–115): đọc secret qua `os.getenv("OPENAI_API_KEY", "")` / `os.getenv("AGENT_API_KEY", "")`, kiểm tra bắt buộc khi `environment == "production"`, và chỉ log JSON metadata (`event`, `question_length`, `client_ip`), tuyệt đối không log secret.

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (dòng 8) — image đầy đủ gồm Debian và toàn bộ bộ công cụ Python/build tools (~1 GB+).
2. **Working directory:** `/app` (dòng 11: `WORKDIR /app`) — mọi lệnh `COPY`, `RUN`, `CMD` phía sau chạy trong thư mục này.
3. **Tại sao `COPY requirements.txt` trước khi `COPY` code?** Tận dụng **Docker layer cache**. File `requirements.txt` ít thay đổi hơn mã nguồn (`app.py`), nên khi chỉ sửa code, Docker tái sử dụng cache tầng `pip install` thay vì tải và cài lại toàn bộ dependencies.
4. **`CMD` vs `ENTRYPOINT`:**
   - `CMD` đặt lệnh/tham số mặc định khi container khởi động và **có thể ghi đè trực tiếp** bằng tham số truyền vào sau tên image trong `docker run`.
   - `ENTRYPOINT` cố định tiến trình chính của container (tham số truyền thêm ở `docker run` hoặc `CMD` sẽ được nối làm đối số cho `ENTRYPOINT`), chỉ ghi đè khi dùng cờ `--entrypoint`.

### Exercise 2.2: Build và test container `develop`

Build từ thư mục gốc repo (`docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .`), chạy container map cổng `8000:8000` và kiểm tra:

```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok","uptime_seconds":21.8,"container":true}

curl -s -X POST "http://127.0.0.1:8000/ask?question=What%20is%20Docker%3F"
# {"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Multi-stage build & Image size comparison

- **Stage 1 (`builder`):** Dùng `python:3.11-slim`, cài `gcc` và `libpq-dev` để compile dependencies, cài gói Python bằng `pip install --no-cache-dir --user` vào `/root/.local`.
- **Stage 2 (`runtime`):** Bắt đầu từ `python:3.11-slim` sạch, tạo user non-root `appuser`, chỉ `COPY --from=builder /root/.local /home/appuser/.local`, copy `main.py` và `utils/mock_llm.py`, cấu hình `HEALTHCHECK` và `CMD ["uvicorn", ...]`.
- **Tại sao image nhỏ hơn?** Loại bỏ hoàn toàn compiler (`gcc`, `libpq-dev`), package cache và lớp base image nặng của Python full, chỉ giữ runtime cần thiết nên vừa gọn nhẹ vừa an toàn hơn.

Kết quả đo bằng `docker images | grep my-agent`:

- **Develop (`my-agent:develop`):** `1.67 GB` (`1,670 MB`, content size `426 MB`)
- **Production (`my-agent:advanced`):** `240 MB` (content size `57.4 MB`)
- **Chênh lệch (giảm):** `1,670 - 240 = 1,430 MB` → giảm **85.6%**

### Exercise 2.4: Docker Compose stack & test qua Nginx

**Sơ đồ kiến trúc các service (`02-docker/production/docker-compose.yml`, network `internal`):**

```text
Client ──(:80)──▶ Nginx (reverse proxy, rate limit 10r/s)
                     │
                     ▼ (proxy_pass http://agent:8000)
                   Agent (FastAPI, port 8000 nội bộ)
                     ├──▶ Redis (:6379, session cache & rate limiting)
                     └──▶ Qdrant (:6333, vector database cho RAG)
```

Trạng thái stack (`docker compose -p k5-day14-docker -f 02-docker/production/docker-compose.yml ps`):

```text
NAME                       IMAGE                   SERVICE   STATUS
k5-day14-docker-agent-1    k5-day14-docker-agent   agent     Up 20 seconds (healthy)
k5-day14-docker-nginx-1    nginx:alpine            nginx     Up 20 seconds
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    qdrant    Up 34 seconds (healthy)
k5-day14-docker-redis-1    redis:7-alpine          redis     Up 33 seconds (healthy)
```

Kết quả test qua Nginx (cổng `80`):

```bash
curl -s http://127.0.0.1/health
# {"status":"ok","uptime_seconds":28.1,"version":"2.0.0","timestamp":"2026-11-26T08:51:19.015301"}

curl -s -X POST http://127.0.0.1/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
# {"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway Deployment (Agent Part 6 — `06-lab-complete/`)

- **Public URL:** https://k5-l3b-day14-tranquangha-2a202603962-deployment-production.up.railway.app
- **Cấu hình trên Railway:** Deploy trực tiếp thư mục `06-lab-complete/` bằng `Dockerfile` multi-stage, nối dịch vụ **Redis** qua `REDIS_URL=${{Redis.REDIS_URL}}`, đặt `AGENT_API_KEY`, `ENVIRONMENT=production`, `RATE_LIMIT_PER_MINUTE=10`, `DAILY_BUDGET_USD=1.0` trên Railway Variables.
- **Screenshots:**
  - Dashboard & Env Vars (đã ẩn key): [screenshots/dashboard.png](screenshots/dashboard.png)
  - Trạng thái chạy `ACTIVE`: [screenshots/running.png](screenshots/running.png)
  - Kết quả tự kiểm tra 4 lệnh CP6: [screenshots/test.png](screenshots/test.png)
- **Kết quả kiểm tra Public URL (4 lệnh chuẩn CP6):**

```text
GET  /health              → 200
GET  /ready               → 200
POST /ask (không API key) → 401
POST /ask (có X-API-Key)  → 200
```

### Exercise 3.2: So sánh `railway.toml` với `render.yaml`

| Tiêu chí | `railway.toml` | `render.yaml` |
| --- | --- | --- |
| **Định dạng & Phạm vi** | **TOML**, gọn nhẹ, cấu hình **cho 1 service** (cách build, start, healthcheck, restart policy). | **YAML (Blueprint / IaC)**, có thể khai báo **cả hệ thống nhiều service** (web service + Redis + `envVars`) trong một file. |
| **Build & Runtime** | Chỉ định `builder = "DOCKERFILE"` (hoặc `NIXPACKS`), `dockerfilePath`. | Khai báo rõ `type: web`, `runtime: docker` (hoặc `python`), `region`, `plan` (`free`), `buildCommand` / `startCommand`. |
| **Biến môi trường & Secret** | Không khai báo env/secret trong `railway.toml` — quản lý riêng trên Dashboard/CLI (`${{Redis.REDIS_URL}}`). | Khai báo trực tiếp danh sách `envVars` trong YAML và hỗ trợ sinh/ẩn secret an toàn (`generateValue: true`, `sync: false`). |
| **Vì sao khác nhau?** | Railway ưu tiên tối giản cấu hình per-service, quản lý biến môi trường và Redis trực tiếp qua Project Canvas/CLI. | Render dùng Blueprint YAML để mô tả toàn bộ stack dưới dạng Infrastructure-as-Code ngay từ Git. |

### Exercise 3.3: GCP Cloud Run CI/CD Pipeline (`03-cloud-deployment/production-cloud-run/`)

- **`cloudbuild.yaml`:** Định nghĩa pipeline CI/CD 4 bước chạy tuần tự (dùng `waitFor`) khi push lên `main`: **(1) `test`** chạy `pytest` trong container `python:3.11-slim`, **(2) `build`** Docker image gắn tag `$COMMIT_SHA` và `:latest` có `--cache-from`, **(3) `push`** image lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`), và **(4) `deploy`** lên Cloud Run region `asia-southeast1` (`--min-instances=1` tránh cold start, `--max-instances=10`, lấy secret từ Secret Manager).
- **`service.yaml`:** File IaC chuẩn Knative (`serving.knative.dev/v1`) mô tả cấu hình runtime của service Cloud Run gồm giới hạn scale (`minScale: 1`, `maxScale: 10`), `containerConcurrency: 80`, CPU/RAM (`limits`/`requests`), inject secret qua `secretKeyRef`, và tách riêng `livenessProbe` (`/health`) với `startupProbe` (`/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

- **API key được kiểm tra ở đâu?** Tại hàm `verify_api_key` (dòng 39–54) đọc header `X-API-Key` bằng `APIKeyHeader(name="X-API-Key", auto_error=False)`, và được gắn vào endpoint `/ask` thông qua `Depends(verify_api_key)` (dòng 70).
- **Điều gì xảy ra nếu thiếu hoặc sai key?** Thiếu header trả về `HTTP 401 Unauthorized`; gửi sai key trả về `HTTP 403 Forbidden` (không vào được logic xử lý LLM).
- **Cách rotate key:** Đọc danh sách key hợp lệ từ biến môi trường (vd hỗ trợ tạm thời cả key cũ và key mới trong khoảng thời gian chuyển tiếp), cập nhật client sang key mới, rồi gỡ key cũ khỏi env và restart/reload service.

Kết quả test thực tế (`AGENT_API_KEY=secret-key-123 python app.py`):

```http
# 1. Không có key → 401
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# 2. Sai key → 403
HTTP/1.1 403 Forbidden
content-type: application/json

{"detail":"Invalid API key."}

# 3. Đúng key → 200
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- **JWT Flow (`auth.py`, `app.py`):** Client gửi `username`/`password` (`student` / `demo123`) tới `POST /auth/token` → server xác thực và ký JWT (`HS256`, hết hạn sau 60 phút, chứa `sub` và `role`). Các request sau gửi `Authorization: Bearer <TOKEN>` → `verify_token` giải mã và kiểm tra chữ ký + thời hạn mà không cần tra database mỗi request.
- **Thuật toán Rate Limit (`rate_limiter.py`):** **Sliding Window Counter** sử dụng `collections.deque` (lưu timestamps các request trong cửa sổ `window_seconds = 60`). Mỗi request mới sẽ loại bỏ các timestamp cũ hơn `now - 60`, kiểm tra số lượng còn lại:
  - **Limit:** `10 requests/phút` cho `user` (`student`), `100 requests/phút` cho `admin` (`teacher`).
  - **Cách phân biệt/bypass cho admin:** Tại `app.py` dòng 141 (`limiter = rate_limiter_admin if role == "admin" else rate_limiter_user`), dựa vào `role` trong JWT payload để chọn giới hạn cao hơn (hoặc bỏ qua check nếu `role == "admin"`).

Kết quả lấy token cho `student`, gọi `/ask` (`200`), kiểm tra `/me/usage` và spam 12 request (đã che `<TOKEN>`):

```http
# Gọi /ask với Bearer <TOKEN> → 200 OK (kèm security headers)
HTTP/1.1 200 OK
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}

# GET /me/usage
{"user_id":"student","date":"2026-11-26","requests":1,"input_tokens":4,"output_tokens":30,"cost_usd":1.9e-05,"budget_usd":1.0,"budget_remaining_usd":0.999981,"budget_used_pct":0.0}
```

Vòng lặp gọi liên tiếp (Request 2 → Request 12) bằng token của `student`:

```text
=== Request 2 ===
HTTP/1.1 200 OK
{"question":"Test 2","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":8,"budget_remaining_usd":3.7e-05}}
...
=== Request 10 ===
HTTP/1.1 200 OK
{"question":"Test 10","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":0,"budget_remaining_usd":0.000181}}
=== Request 11 ===
HTTP/1.1 429 Too Many Requests
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":46}}
=== Request 12 ===
HTTP/1.1 429 Too Many Requests
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":46}}
```

### Exercise 4.4: Cost Guard (`04-api-gateway/production/cost_guard.py`)

- **Cách triển khai:**
  1. **Trước khi gọi LLM (`check_budget`):** Đọc tổng chi phí đã dùng trong ngày/tháng (demo lưu trong `UsageRecord` in-memory; production lưu trong **Redis** theo key `budget:{user_id}:{YYYY-MM-DD}` hoặc theo tháng). Nếu đạt hoặc vượt ngưỡng (`daily_budget_usd = $1.0` hoặc global `$10.0`), chặn ngay bằng **`HTTP 402 Payment Required`** (hoặc `503` cho global limit) trước khi phát sinh chi phí gọi LLM; cảnh báo khi đạt `80%`.
  2. **Sau khi gọi LLM (`record_usage`):** Đếm `input_tokens` và `output_tokens`, nhân với đơn giá từng loại (`$0.00015 / 1K input`, `$0.0006 / 1K output`), rồi cộng dồn vào Redis bằng lệnh atomic `INCRBYFLOAT` kèm `EXPIRE` để tự reset sang chu kỳ mới.
- **Tại sao cần cả Rate Limit lẫn Cost Guard?**
  - **Rate Limit** bảo vệ **tốc độ truy cập** (ngăn spam/DDoS, quá tải CPU/worker trong từng phút).
  - **Cost Guard** bảo vệ **ngân sách tiền thật** (vì kẻ tấn công vẫn có thể gọi chậm dưới ngưỡng rate limit nhưng gửi prompt dài/chạy đều 24/7 làm cạn tiền API).

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health & Readiness Checks (`05-scaling-reliability/develop/app.py`)

- **Phân biệt Liveness (`/health`) vs Readiness (`/ready`):**
  - `GET /health` (**Liveness probe**): Kiểm tra tiến trình app còn sống hay không (dòng 104–144). Platform dùng để quyết định có cần restart container hay không — **không** nên để `/health` fail chỉ vì một service phụ như Redis bị gián đoạn tạm thời.
  - `GET /ready` (**Readiness probe**): Kiểm tra app đã sẵn sàng nhận traffic chưa (khởi động xong model/kết nối Redis chưa, có đang shutdown không — dòng 147–168). Trả `200` khi sẵn sàng và `503` khi chưa sẵn sàng để load balancer tạm ngắt đẩy traffic mới vào instance này.

Kết quả test thực tế:

```json
// GET /health
{"status":"ok","uptime_seconds":18.1,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T09:29:28.431079+00:00","checks":{"memory":{"status":"ok","used_percent":8.7}}}

// GET /ready
{"ready":true,"in_flight_requests":1}
```

### Exercise 5.2: Graceful Shutdown

- **Cơ chế hoạt động:** Khi nhận `SIGTERM` (`handle_sigterm` + `uvicorn` `lifespan`), server đặt `_is_ready = False` (để `/ready` trả `503`, load balancer ngừng gửi request mới), tiếp tục xử lý hết các request đang chạy dở (`_in_flight_requests`, tối đa `timeout_graceful_shutdown=30`), rồi mới đóng hoàn toàn.
- **Kết quả test thực tế:** Gửi 2 request `POST /ask` chạy song song (mock LLM delay 3s) rồi gửi `kill -SIGTERM` sau 0.5s:

```http
HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}

HTTP/1.1 200 OK
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

Log server ở Terminal 1 xác nhận cả 2 request đều trả `200 OK` trước khi tắt hoàn toàn:

```text
INFO:     Shutting down
INFO:     127.0.0.1:57456 - "POST /ask?question=docker HTTP/1.1" 200 OK
INFO:     127.0.0.1:57454 - "POST /ask?question=hello HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-26 09:30:00,214 INFO 🔄 Graceful shutdown initiated...
2026-11-26 09:30:00,214 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [1543]
2026-11-26 09:30:00,214 INFO Received signal 15 — uvicorn will handle graceful shutdown
```

### Exercise 5.3, 5.4 & 5.5: Stateless Design, Load Balancing & Test (`05-scaling-reliability/production/`)

- **Vì sao state lưu trong RAM hỏng khi chạy nhiều instance?** Khi scale lên 3 container (`--scale agent=3`), mỗi container có vùng nhớ RAM riêng. Nếu lưu `conversation_history` trong dict in-memory, request 1 vào `instance-1` còn request 2 bị Nginx round-robin sang `instance-2` sẽ bị mất lịch sử hội thoại.
- **Giải pháp:** Lưu toàn bộ session và history ra **Redis** dùng chung (`save_session` dùng `setex` với TTL 3600s, `load_session` dùng `get`), giúp mọi instance đều phục vụ được bất kỳ user nào.

Trạng thái stack `docker compose -p k5-day14-scaling ps` (3 agent + nginx cổng `8080` + redis):

```text
NAME                       SERVICE   STATUS
k5-day14-scaling-agent-1   agent     Up (healthy)
k5-day14-scaling-agent-2   agent     Up (healthy)
k5-day14-scaling-agent-3   agent     Up (healthy)
k5-day14-scaling-nginx-1   nginx     Up (0.0.0.0:8080->80/tcp)
k5-day14-scaling-redis-1   redis     Up (healthy)
```

Kết quả chạy `python test_stateless.py`:

```text
Session ID: 60c88cfd-e7af-4ee0-8ea6-cb46d78ca2eb

Request 1: [instance-83aa78]  (What is Docker?)
Request 2: [instance-0ad1ce]  (Why do we need containers?)
Request 3: [instance-0948ed]  (What is Kubernetes?)
Request 4: [instance-83aa78]  (How does load balancing work?)
Request 5: [instance-0ad1ce]  (What is Redis used for?)

Total requests: 5
Instances used: {'instance-83aa78', 'instance-0ad1ce', 'instance-0948ed'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

- **Giải thích:** Nginx phân tải đều 5 request qua cả 3 container agent (`instance-83aa78`, `instance-0ad1ce`, `instance-0948ed`), nhưng toàn bộ 5 lượt hỏi-đáp (10 messages) vẫn giữ nguyên vẹn vì state được lưu tập trung tại Redis.

---

## Part 6: Production Readiness Checklist (`check_production_ready.py`)

Kết quả chạy đầy đủ `python check_production_ready.py` trong `06-lab-complete/` trên WSL2 (có Docker):

- **Kích thước Docker image:** `238 MB` (build `22s`)
- **Graceful shutdown:** `SIGTERM` exit code `0`; `docker stop` exit code `0` (`0.7s`)
- **Structured logging:** `7 dòng JSON` hợp lệ

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

- **CP1 (Part 1):**
  - *Đã hỏi AI:* Phân tích các anti-pattern trong `01-localhost-vs-production/develop/app.py`, đối chiếu với `01-localhost-vs-production/production/app.py` và `config.py`, hướng dẫn chạy trong môi trường WSL2 venv.
  - *Đã nhận:* Danh sách 7 anti-pattern kèm số dòng, bảng so sánh theo 12-Factor, lệnh test chuẩn cho bản `develop` (query param) và `production` (JSON).
  - *Tự kiểm tra:* Tự tạo virtualenv trong WSL2 (`posix`, Python 3.12.3), chạy trực tiếp cả 2 server `develop` và `production`, tự gọi `curl` vào `/ask`, `/health`, `/ready` và xác nhận kết quả thực tế trước khi ghi vào bài.
- **CP2 (Part 2):**
  - *Đã hỏi AI:* Hướng dẫn giải quyết xung đột cổng 8000 (`wslrelay.exe`), lỗi giới hạn Docker Hub `429 Too Many Requests`, giải thích `02-docker/develop/Dockerfile`, `02-docker/production/Dockerfile`, `docker-compose.yml` và tính % giảm dung lượng.
  - *Đã nhận:* Các lệnh build/run từ gốc repo và cấu trúc giải thích multi-stage + sơ đồ Docker Compose.
  - *Tự kiểm tra:* Tự build `my-agent:develop` (`1.67GB`) và `my-agent:advanced` (`240MB`), tự chạy container và Docker Compose stack 4 service, tự gọi `curl` kiểm tra `/health` và `/ask` qua cả container lẫn Nginx trước khi ghi số đo thật vào bài.
- **CP3 (Part 4):**
  - *Đã hỏi AI:* Hướng dẫn lệnh test đúng cho bản `04-api-gateway/develop` và `production` theo lưu ý K5 (`/auth/token`, `student`/`demo123`), phân tích thuật toán rate limiter và cách triển khai Cost Guard.
  - *Đã nhận:* Các lệnh `curl -i` kiểm tra `401`, `403`, `200`, vòng lặp chạm ngưỡng `429`, và giải thích luồng JWT + Cost Guard.
  - *Tự kiểm tra:* Tự chạy cả 2 server trên WSL2, tự lấy JWT token, kiểm tra `/me/usage` và chạy vòng lặp 12 request để xác nhận chuyển từ `200` sang `429` đúng tại request thứ 11 (đã che token trước khi lưu).
- **CP4 (Part 5):**
  - *Đã hỏi AI:* Giải thích Liveness vs Readiness, cơ chế Graceful Shutdown, thiết kế stateless với Redis và lệnh chạy stack 3 instance theo lưu ý K5 (`-p k5-day14-scaling`, cổng `8080`, `POST /chat`).
  - *Đã nhận:* Lệnh test song song `curl` + `kill -SIGTERM` và các bước chạy `docker compose` scale 3 agent + `test_stateless.py`.
  - *Tự kiểm tra:* Tự chạy test graceful shutdown xác nhận cả 2 request đang chạy vẫn trả `200 OK` sau `SIGTERM`, tự scale 3 container agent và chạy `test_stateless.py` xác nhận traffic đi qua 3 instance khác nhau nhưng vẫn giữ đủ 10 messages trong Redis.
- **CP5 (Part 6):**
  - *Đã hỏi AI:* Thiết kế và triển khai toàn bộ các TODO trong `06-lab-complete/` (config env, Redis client, API key auth, Redis sliding-window rate limiter, Redis cost guard, structured JSON logging, lifespan graceful shutdown, multi-stage Dockerfile, docker-compose, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`).
  - *Đã nhận:* Kế hoạch chi tiết và mã nguồn cho 12 file trong `06-lab-complete/`.
  - *Tự kiểm tra:* Tự chạy `python check_production_ready.py` đầy đủ trong WSL2 có Docker và xác nhận đạt `12/12 tiêu chí · 43/43 checks passed` (`PASS 12/12`).
- **CP6 (Part 3):**
  - *Đã hỏi AI:* Hướng dẫn deploy `06-lab-complete/` lên Railway kèm Redis, kiểm tra an toàn ảnh chụp màn hình trước khi lưu, so sánh `railway.toml` vs `render.yaml` và tóm tắt pipeline Cloud Run (`cloudbuild.yaml`, `service.yaml`).
  - *Đã nhận:* Các bước cấu hình Root Directory, Variables trên Railway, 4 lệnh test CP6 không lộ key, mẫu `DEPLOYMENT.md` và bảng so sánh cấu hình.
  - *Tự kiểm tra:* Tự deploy lên Railway kèm Redis, tự chạy 4 lệnh `curl` kiểm tra Public URL xác nhận mã HTTP `200`, `200`, `401`, `200` và kiểm tra body JSON từ `/ready` và `/ask`.
- **CP7 (Part 7 Bước 1):**
  - *Đã hỏi AI:* Phân tích 9 file JSON load test/eval ban đầu, đề xuất bổ sung 2 entry (`["hpa", "kubernetes", "autoscal"]` và `["jwt"]`) vào `KNOWLEDGE_BASE` trong `mock_llm.py`, tạo CI quality gate `.github/workflows/eval.yml` và điền `BENCHMARK_REPORT.md` Mục 1–3.
  - *Đã nhận:* Mã nguồn cập nhật `mock_llm.py` (develop & production), `.github/workflows/eval.yml` và bảng số liệu đối chiếu khớp file JSON.
  - *Tự kiểm tra:* Tự chạy toàn bộ load test (`c=1, 10, 50, 100` và `MOCK_SLOW_RATE=0, 0.03, 0.1`), tự chạy eval `v1`, `v2` và `eval_v2_fixed.json` xác nhận đạt `23/23 (100.0%)` với `0` regression.
- **CP8 (Part 7 Bước 2):**
  - *Đã hỏi AI:* Debug lỗi `ModuleNotFoundError: No module named 'uvicorn'` trong `06-lab-complete/benchmark-observability/production/Dockerfile`, hướng dẫn vận hành full stack (`-p k5-day14-observability`), chạy đo kiểm bổ sung Exercise 7.4/7.6 và hoàn thiện `BENCHMARK_REPORT.md`.
  - *Đã nhận:* Bổ sung `ENV PYTHONUSERBASE=/home/agent/.local` vào `production/Dockerfile` (khớp với pattern ở Part 5), cấu trúc đối chiếu số liệu từ CSV/Prometheus/Jaeger.
  - *Tự kiểm tra:* Tự chạy `locust` headless tạo `scale_1_stats.csv` và `scale_3_stats.csv` sau khi fix Dockerfile, tự chạy Locust UI xem Grafana, truy vết trace chậm (`2dc21e16efa3cfe05c6661336f75a1f5`) & trace lỗi (`1062d42657c7929632ca419ad78233f0`) kèm JSON log, kích hoạt 2 alert `AgentHighErrorRate` + `AgentHighLatencyP95` cùng firing trên Prometheus (`promtool test rules` → `SUCCESS`).
