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

Job CI khởi chạy agent `v2` với `MOCK_ERROR_RATE=0` và chạy `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85`. Script `run_eval.py` trả về **exit code `1`** nếu `accuracy < 0.85` hoặc có câu nào bị regression so với baseline, làm step CI fail và tự động chặn không cho merge Pull Request.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing** (`prometheus-alert-firing.png`)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

*(Đang chờ hoàn thành CP8)*

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

*(Đang chờ hoàn thành CP8)*

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

*(Đang chờ hoàn thành CP8)*
