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

*(Đang chờ hoàn thành CP2)*

---

## Part 3: Cloud Deployment

*(Đang chờ hoàn thành CP6)*

---

## Part 4: API Security

*(Đang chờ hoàn thành CP3)*

---

## Part 5: Scaling & Reliability

*(Đang chờ hoàn thành CP4)*

---

## Part 6: Production Readiness Checklist (`check_production_ready.py`)

*(Đang chờ hoàn thành CP5)*

---

## AI Log

- **CP1 (Part 1):**
  - *Đã hỏi AI:* Phân tích các anti-pattern trong `01-localhost-vs-production/develop/app.py`, đối chiếu với `01-localhost-vs-production/production/app.py` và `config.py`, hướng dẫn chạy trong môi trường WSL2 venv.
  - *Đã nhận:* Danh sách 7 anti-pattern kèm số dòng, bảng so sánh theo 12-Factor, lệnh test chuẩn cho bản `develop` (query param) và `production` (JSON).
  - *Tự kiểm tra:* Tự tạo virtualenv trong WSL2 (`posix`, Python 3.12.3), chạy trực tiếp cả 2 server `develop` và `production`, tự gọi `curl` vào `/ask`, `/health`, `/ready` và xác nhận kết quả thực tế trước khi ghi vào bài.
