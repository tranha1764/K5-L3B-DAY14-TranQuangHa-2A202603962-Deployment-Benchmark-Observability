# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được lấy trực tiếp từ các file JSON trong `reports/` và CSV trong `benchmark-results/`, không ước lượng.

**Họ tên:** Tran Quang Ha (2A202603962)
**Ngày chạy:** 2026-11-26
**Môi trường:** Windows 11 + WSL2 Ubuntu (Python 3.12.3, Docker 29.8.1 / Docker Desktop)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < `500` ms | Đảm bảo 95% người dùng nhận phản hồi trong dưới nửa giây; phù hợp mức mặc định của `load_test.py` khi dùng mock LLM (~150–240ms ở tải bình thường). |
| Error rate `/ask` | < `2.0` % | Tương ứng error budget 2% để dung sai lỗi upstream tạm thời của mock LLM (`MOCK_ERROR_RATE=0.01`, ~1%). |
| Accuracy trên golden dataset | ≥ `85` % | Đảm bảo chất lượng trả lời đủ tin cậy trước khi merge/deploy (quality gate trong `.github/workflows/eval.yml`, đặt mục tiêu cao hơn nữa là 100% sau khi bổ sung knowledge base). |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### Exercise 7.1 — Metrics & Cardinality (`develop/app.py`)

- **3 loại metric quan sát được từ `/metrics`:**
  - `http_requests_total{method="POST",route="/ask",status="200"} 1.0` → **Counter** (chỉ tăng, dùng với `rate()` để tính RPS).
  - `agent_in_flight_requests 0.0` → **Gauge** (lên xuống, theo dõi số request đang xử lý tại thời điểm hiện tại).
  - `http_request_duration_seconds_bucket{...}` → **Histogram** (phân bố độ trễ vào các bucket để tính `p50`/`p95`/`p99` qua `histogram_quantile()`).
- **Vì sao middleware `observe_requests` dùng `route.path` (và `unmatched`) thay vì `request.url.path`?** Nếu dùng URL thô làm label, khi bot quét gửi hàng nghìn đường dẫn lạ như `/wp-admin`, `/.env`, `/a1b2c3`, mỗi URL tạo ra một time series mới làm **cardinality bùng nổ** và ngốn hết RAM của Prometheus. Dùng `route.path` template và gom URL không khớp vào `unmatched` giúp số lượng giá trị label hữu hạn.
- **Bổ sung metric `agent_question_length_chars` (`Histogram`) vào `develop/app.py` và kiểm chứng `/metrics` sau khi gọi `POST /ask`:**

```text
http_requests_total{method="POST",route="/ask",status="200"} 1.0
agent_in_flight_requests 0.0
agent_question_length_chars_bucket{le="20.0"} 0.0
agent_question_length_chars_bucket{le="50.0"} 1.0
agent_question_length_chars_bucket{le="100.0"} 1.0
agent_question_length_chars_bucket{le="200.0"} 1.0
agent_question_length_chars_bucket{le="500.0"} 1.0
agent_question_length_chars_bucket{le="1000.0"} 1.0
agent_question_length_chars_bucket{le="2000.0"} 1.0
agent_question_length_chars_bucket{le="+Inf"} 1.0
agent_question_length_chars_count 1.0
agent_question_length_chars_sum 40.0
```

### 2.1 Concurrency vs latency (agent v2)

*(Nguồn: `reports/load_v2_c1.json`, `load_v2_c10.json`, `load_v2_c50.json`, `load_v2_c100.json`, mỗi mức 300 requests, SLO p95 ≤ 500ms, error rate ≤ 2.0%)*

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.53 | 192.2 | 216.3 | 1709.2 | 0.67% (`2/300`) | PASS |
| 10 | 41.01 | 189.7 | 216.3 | 1675.5 | 0.67% (`2/300`) | PASS |
| 50 | 109.46 | 192.4 | 236.1 | 1700.5 | 0.33% (`1/300`) | PASS |
| 100 | 66.57 | 303.7 | 2618.0 | 3216.9 | 0.33% (`1/300`) | FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không. Từ concurrency `1` → `10` → `50`, RPS tăng gần tuyến tính (`4.53` → `41.01` → `109.46` req/s) do I/O bất đồng bộ (`async`) tận dụng thời gian chờ LLM. Tuy nhiên khi tăng lên `100`, một process Python đơn lẻ bắt đầu bị nghẽn hàng đợi/event loop và contention, khiến throughput **tụt xuống `66.57` req/s** còn `p95` vọt từ `236.1 ms` lên **`2618.0 ms`** (vượt xa SLO `500 ms`).

### 2.2 Tail latency

*(Nguồn: `reports/load_v2_slow_0.json`, `load_v2_slow_0.03.json`, `load_v2_slow_0.1.json`, 300 requests, concurrency=20)*

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 188.8 | 214.6 | 219.9 |
| 0.03 (mặc định) | 257.4 | 222.1 | 1701.8 |
| 0.1 | 327.6 | 1682.1 | 1711.8 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

`p99` (và `p95` khi tỉ lệ chậm > 5%) nhạy nhất với request chậm: ở `MOCK_SLOW_RATE=0.03`, `avg` chỉ tăng thêm `68.6 ms` (`188.8` → `257.4 ms`) trông vẫn rất nhanh, nhưng **`p99` nhảy vọt gần 8 lần** lên `1701.8 ms`. Khi tăng lên `0.1` (10% request chậm), cả `p95` cũng vọt lên `1682.1 ms` trong khi `avg` mới là `327.6 ms`. Vì **average bị kéo xuống bởi 90–97% request nhanh và che giấu trải nghiệm tệ của nhóm user chậm**, SLO bắt buộc phải đặt theo percentile (`p95`/`p99`).

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

*(Nguồn: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`)*

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.1 | 108.8 | 113.7 |
| Tổng cost (USD) | $0.000405 | $0.000758 | $0.000790 |
| Cost / câu đúng (USD) | $0.00040455 | $0.00003607 | $0.00003436 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry với từ khóa `["jwt"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` giải thích JWT là token có chữ ký số và thời điểm hết hạn, khác với API key cố định. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry với từ khóa `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` mô tả Kubernetes HPA scale dựa trên CPU, memory hoặc custom metrics. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

Agent `v2` (có bước retrieval RAG) tiêu tốn gấp ~1.9 lần token mỗi câu (`108.8` vs `57.1` tokens) và tổng chi phí cũng cao hơn ~1.87 lần (`$0.000758` vs `$0.000405`), đồng thời thêm một chút latency ở bước tìm tài liệu (`MOCK_RETRIEVAL_MS` ~20ms; `p50` `189.8ms` vs `155.4ms`). Đổi lại, accuracy tăng vọt từ **4.35%** lên **91.30%** (và **100%** sau khi sửa KB), khiến **chi phí trên mỗi câu trả lời đúng (`cost_per_correct_usd`) giảm hơn 11 lần** (`$0.00003607` so với `$0.00040455`).

**CI Quality Gate (`.github/workflows/eval.yml`):**

Eval local với `--baseline` đã xác minh agent `v2` sau khi sửa `KNOWLEDGE_BASE` đạt **100.0% (23/23)** và **0 regression** (`eval_v2_fixed.json`). Về phần tự động hóa, workflow `.github/workflows/eval.yml` được cấu hình chạy khi có `pull_request` để kiểm tra ngưỡng `--min-accuracy 0.85` (hiện GitHub Actions chưa có lượt chạy do repo chỉ push trực tiếp lên `main`). Để bắt regression trên CI cần truyền thêm `--baseline`, và để tự động chặn merge cần bật job `eval` làm required status check trong cài đặt branch protection của GitHub.

---

## 4. Observability stack (production)

### 4.1 Screenshot & Quan sát Grafana (Exercise 7.4)

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals — `screenshots/grafana-dashboard.png`)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian — `screenshots/jaeger-slow-trace.png`)
- [x] Một trace lỗi trong Jaeger (có event `exception` — `screenshots/jaeger-error-trace.png`)
- [x] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing** (`screenshots/prometheus-alert-firing.png`)

**Trả lời Exercise 7.4 (số đo thực tế từ Grafana & Prometheus):**
- **Latency & tail latency:** Trên dashboard tải bình thường (`screenshots/grafana-dashboard.png`), `Latency p95 = 289.38 ms`, `Traffic = 17.1 req/s`, `Error rate = 0.86%`, `Instances up = 2`, nhưng đường `p99` trên biểu đồ vọt lên `~1.7–1.8 s`. Khi bật fault injection (`MOCK_SLOW_RATE=0.3`), `avg = 502.7 ms` trong khi `p95 = 1.896 s` — khoảng cách lớn giữa `avg` và `p95/p99` cho thấy một phần nhỏ request gặp tail latency cao phía LLM.
- **Chia tải theo instance:** Prometheus ghi nhận `172.21.0.3:8000` đạt `7.51 req/s` và `172.21.0.8:8000` đạt `8.08 req/s` → Nginx round-robin phân phối lưu lượng khá đều cho 2 instance.
- **Input vs Output tokens/s:** `input = 815.0 tokens/s` lớn hơn gần gấp đôi `output = 426.3 tokens/s` vì agent `v2` ghép thêm `SYSTEM_PROMPT` và đoạn tài liệu retrieval từ `KNOWLEDGE_BASE` vào prompt đầu vào.
- **`curl -i http://127.0.0.1:8080/metrics`:** Trả về **`HTTP/1.1 404 Not Found`** (từ Nginx). `nginx.conf` cố tình chặn `/metrics` từ bên ngoài để tránh lộ thông tin nội bộ (route, lưu lượng, chi phí); chỉ Prometheus nằm trong mạng nội bộ `obs_net` mới scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống"

*(Đã chạy unit test alert rules: `promtool test rules /p/alert_rules_test.yml` → **`SUCCESS`**)*

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`, đạt `17.45%–19.53%`) | ~60s sau khi vượt 5% (~75–90s từ lúc đổi env) | *Error rate* & *Requests/s theo status code* (`503`) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`, đạt `1.893s–1.905s`) | ~120s sau khi p95 > 1s (~135–150s từ lúc đổi env) | *Latency p95* & *Latency /ask — p50 / p95 / p99* |
| C | `LLM_MODEL=mock-llm-large` / burn rate cao | `LLMCostBurnRateHigh` (`for: 2m`, ngưỡng `> $2/giờ`) | Đã quan sát **`FIRING`** ở nhóm `agent-cost` (~2–3 phút theo `for: 2m`) | *LLM cost (1h)* & *Cost burn rate (USD/giờ)* (đạt đỉnh `~$6/giờ`) |
| D | `docker pause` 1 instance | `AgentInstanceDown` (`for: 30s`, `up == 0`) | ~10s scrape timeout → `pending` (`38.1s` đang `pending`, ~40–45s tới `firing`) | *Instances up* & *Requests/s theo instance* |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** | Không firing | *Retrieval hit ratio* (mất), *Tokens/s* (giảm), bảng *Instances* (`v1`) |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào? (Và vì sao lỗi 504 ở Nginx không hiện trên metric của agent?)**

- **Cách phát hiện suy giảm chất lượng như thí nghiệm E:** Các alert hạ tầng (error rate, latency, `up`) chỉ đo sức khỏe kỹ thuật (agent vẫn trả `200 OK` nhanh), nên hoàn toàn mù trước lỗi chất lượng câu trả lời. Phải kết hợp: **(1)** chạy **Eval + Quality Gate** trên golden dataset trong CI/CD trước khi deploy (như `.github/workflows/eval.yml`), **(2)** theo dõi metric nghiệp vụ/RAG như `retrieval_hit_ratio` (cảnh báo khi tụt đột ngột), và **(3)** đánh giá chất lượng định kỳ trên mẫu traffic production (LLM-as-judge / phản hồi người dùng).
- **Vì sao lỗi 504 ở Nginx (khi instance bị pause) không hiện trên metric của agent:** Lỗi `504 Gateway Timeout` do **Nginx** tự sinh ra khi chờ quá `proxy_read_timeout` và ngắt kết nối, request chưa bao giờ được agent xử lý xong nên counter `http_requests_total{status=~"5.."}` bên trong agent không đếm được. Vì vậy trong production cần giám sát thêm ở tầng Load Balancer/Nginx và đặt synthetic check từ bên ngoài.

### 4.3 Debug bằng trace

**1. Trace chậm nhất tìm được trong Jaeger (`screenshots/jaeger-slow-trace.png`):**

- `trace_id`: `ce5bd10d122cacc48ff24e30684f2879`
- Tổng thời gian (`POST /ask`): `1699.3 ms` (`~1.70 s`; `agent.run`: `1696.7 ms`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1672.9 ms`, chiếm **98.4%** tổng thời gian; bước `agent.retrieve_context` chỉ mất `23.2 ms` — chứng minh nút thắt là tail latency phía LLM chứ không phải retrieval).
- Dòng log JSON tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-26T15:44:36.151054+00:00", "level": "INFO", "service": "observable-agent", "instance": "fdc205d35d51", "event": "llm_call", "trace_id": "ce5bd10d122cacc48ff24e30684f2879", "span_id": "023d6a93045dc4fa", "request_id": "01630a4ca717", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 81, "output_tokens": 46, "cost_usd": 4e-05, "llm_ms": 1672.9}
{"ts": "2026-11-26T15:44:36.151531+00:00", "level": "INFO", "service": "observable-agent", "instance": "fdc205d35d51", "event": "http_request", "trace_id": "ce5bd10d122cacc48ff24e30684f2879", "span_id": "023d6a93045dc4fa", "request_id": "01630a4ca717", "method": "POST", "route": "/ask", "status": 200, "ms": 1698.6}
```

**2. Trace lỗi khớp log JSON (`screenshots/jaeger-error-trace.png`):**

- `trace_id`: `1062d42657c7929632ca419ad78233f0` (Duration: `98.7 ms`, `http.status_code = 503`, event `exception`: `Upstream LLM error: 503 Service Unavailable (mock)`)
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-26T15:08:01.852694+00:00", "level": "INFO", "service": "observable-agent", "instance": "9376aa974336", "event": "llm_error", "trace_id": "1062d42657c7929632ca419ad78233f0", "span_id": "03db3651e2d46843", "request_id": "12f55644b3dd", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-26T15:08:01.852926+00:00", "level": "INFO", "service": "observable-agent", "instance": "9376aa974336", "event": "http_request", "trace_id": "1062d42657c7929632ca419ad78233f0", "span_id": "03db3651e2d46843", "request_id": "12f55644b3dd", "method": "POST", "route": "/ask", "status": 503, "ms": 98.2}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

*(Nguồn: `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`, dòng `Aggregated`)*

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 61.43 | 190 | 230 | 1700 | 70 / 7869 (0.89%) |
| 3 | 61.07 | 190 | 220 | 1700 | 61 / 7885 (0.77%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Scale từ `1` lên `3` instance giữ nguyên RPS (`~61 req/s`) và hầu như **không làm thay đổi `p95`**: ở dòng `Aggregated` (gộp `/ask` và `/health`), `p95` giảm nhẹ từ `230 ms` → `220 ms`, còn xét riêng endpoint `POST /ask` thì `p95` vẫn giữ nguyên **`230 ms` → `230 ms`** (`p50` giữ `190 ms`, `p99` giữ `1700 ms`). Lý do gồm hai điểm:
1. Ở mức tải 100 user có `wait_time = between(0.5, 2)` giây trong `locustfile.py`, tổng lưu lượng sinh ra chỉ khoảng ~61 req/s — 1 instance FastAPI bất đồng bộ (`async`) chưa bị bão hòa CPU, nên tăng lên 3 instance không làm RPS tăng thêm.
2. **Nút thắt nằm ở latency phía upstream LLM** (`MOCK_LATENCY_MS=120ms + jitter + tail 1500ms`, thể hiện rõ trên Jaeger ở span `chat mock-llm-small` chiếm ~94% thời gian xử lý). Việc tăng số container agent chỉ tăng khả năng chịu tải đồng thời khi CPU bão hòa, không rút ngắn được thời gian chờ mỗi lần gọi LLM.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Không đánh giá hiệu năng bằng latency trung bình:** `average` che giấu nhóm user chậm; cần dùng `p95`/`p99` để đặt SLO và dùng load test tách riêng khỏi bộ eval nhỏ.
  2. **Ba trụ cột Observability bổ trợ nhau:** Metrics (Prometheus/Grafana) báo *có vấn đề gì*, Traces (OpenTelemetry/Jaeger) chỉ *chậm hoặc lỗi ở span nào*, và JSON Logs gắn `trace_id` giúp *đối chiếu chính xác từng request lỗi*.
  3. **Hạ tầng xanh không đồng nghĩa chất lượng tốt:** Khi đổi agent `v2` về `v1`, mọi alert hạ tầng đều im lặng nên bắt buộc phải có Eval & Quality Gate trong CI/CD để chặn regression chất lượng.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - Thêm cảnh báo **chất lượng & retrieval**: tỉ lệ fallback/retrieval miss (`retrieval_hit_ratio < threshold`), đánh giá định kỳ (LLM-as-judge) trên mẫu traffic thật.
  - Thêm **giám sát tầng load balancer / synthetic monitoring** từ bên ngoài (vd Blackbox Exporter) để bắt các lỗi timeout `504` hoặc `502` tại Nginx mà metric nội bộ của agent không nhìn thấy, kèm Alertmanager gửi cảnh báo về Slack/PagerDuty.
