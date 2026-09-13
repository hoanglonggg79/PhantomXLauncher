# PhantomX Launcher — GLOBAL CONSTANTS & RULES

> **Nguồn chân lý (single source of truth)** cho mọi phiên làm việc. Đọc file này TRƯỚC khi viết code.
> Thứ tự ưu tiên khi có xung đột: **code thực tế > file này > `CONTEXT.md` / `Update.md`**.
> Cập nhật: 2026-09-02 · Dự án: migration PyQt6 (`scr/`) → Tauri 2 + FastAPI Sidecar + React/TS (`app/` + `sidecar/`)

---

## 0. Kiến trúc 3 tầng

| Tầng | Thư mục | Stack | Vai trò |
| --- | --- | --- | --- |
| Frontend | `app/src/` | React 19, Vite 7, TS 5.8, Tailwind v4, shadcn/Radix, Zustand 5, framer-motion, axios | UI, state, SSE listener |
| Desktop shell | `app/src-tauri/` | Tauri 2 (Rust) | Spawn + giám sát sidecar, handshake, giữ `port`/`token` trong Tauri State |
| Backend | `sidecar/` | Python, FastAPI, uvicorn, loguru, sse-starlette | Toàn bộ business logic; bọc `scr/core.py` qua `core_bridge.py` |
| Legacy | `scr/` | PyQt6 | **Chỉ đọc để tham khảo logic.** `core.py` được reuse; UI PyQt6 KHÔNG port trực tiếp |

Luồng khởi động: Tauri spawn sidecar → Python bind port ngẫu nhiên (127.0.0.1) → in `PHANTOMX_READY:<port>:<token>` ra **stdout** → Rust parse, lưu State → frontend gọi `invoke('get_sidecar_info')` → mọi REST/SSE dùng `port` + `token` đó.

**stdout của sidecar là kênh handshake — TUYỆT ĐỐI không `print()` gì khác ra stdout.** Log đi stderr + file.

---

## 1. RULE 1 — Async & SSE (BẮT BUỘC)

Mọi tác vụ chạy lâu (download, verify hash, install mod/modpack, tải Java runtime, clone instance) **PHẢI**:

1. Chạy trên **background thread** — dùng `sidecar/services/tasks.py:start_task(fn)`, không block event loop.
2. Endpoint trả về ngay `202 {"task_id": "...", ...}`.
3. Stream tiến độ qua SSE `GET /api/events/{task_id}` — frame `progress` / `log` / `complete`.
4. Luôn phát frame **`complete`** (kể cả khi lỗi: `success: false`) — stream đóng sau `complete`.

Bắt buộc phía Frontend:

* **Heartbeat**: ping/keep-alive mỗi **5s**; nếu không có frame nào trong khoảng timeout → coi là chết, hiện lỗi, giải phóng UI. Không được để spinner quay vô hạn.
* **Nút "Cancel Task"**: mọi tác vụ đang chạy phải huỷ/reset state được từ UI (`TaskContext.cancel()` + endpoint cancel).
* Task cụt (mất kết nối, sidecar OOM/crash) phải được xử lý như `complete{success:false}`.

Không dùng: long-polling, blocking REST call, `await` trực tiếp một job vài phút trong handler.

---

## 2. RULE 2 — Pathing & Portable Mode

Thứ tự resolve storage root, thực hiện lúc startup Python — **helper duy nhất: `sidecar/utils/path_resolver.py`**:

```
1. $PHANTOMX_DATA_DIR              → override tuyệt đối (dành cho test/CI)
2. <thư mục executable>/PhantomXData  → khi có file `portable.txt` cạnh exe (USB-friendly)
3. %LOCALAPPDATA%\PhantomXTeam\PhantomX\   → mặc định
```

* **TUYỆT ĐỐI KHÔNG ghi file cạnh file `.exe`** khi không ở portable mode (instances, configs, logs, runtimes, cache).
* Constants: `APP_NAME = "PhantomX"`, `APP_AUTHOR = "PhantomXTeam"`.
* Layout: `<root>/instances/`, `<root>/logs/sidecar.log`, `<root>/runtimes/`, `<root>/cache/`, `<root>/config.json`.
* Mọi module phải lấy đường dẫn từ `path_resolver.get_base_dir()` (hoặc `get_log_dir/get_instances_dir/...`), không tự ghép path, không gọi `platformdirs` trực tiếp.
* Root luôn là **đường dẫn tuyệt đối**, kể cả portable mode: cwd của sidecar do Rust shell quyết định nên relative path sẽ resolve sai.
* `sys._MEIPASS` chỉ được dùng để **tìm marker**, không bao giờ làm data root (onefile temp dir bị xoá khi thoát).
* Lưu ý test: trên Windows `platformdirs` **bỏ qua** biến `LOCALAPPDATA` khi override → sandbox test bằng `PHANTOMX_DATA_DIR` + `path_resolver.reset_cache()` (các getter được `lru_cache`).

---

## 3. RULE 3 — Windows File Locking

Windows lock file rất chặt: `.jar` đang được Minecraft mở hoặc Defender đang scan → `PermissionError: [WinError 5]`.

* Mọi thao tác file trong Python (`rename`, `replace`, `remove`, `unlink`, `rmtree`, `copy`) **PHẢI** đi qua `sidecar/utils/file_ops.py` — không gọi `os.remove`/`shutil` trực tiếp.
* API: `safe_file_operation(op, ...)` trả `FileOpResult(ok, locked, skipped, attempts, error, value)` và **không bao giờ raise**. Wrapper sẵn có: `safe_delete`, `safe_rename`, `safe_copy`, `safe_copytree`, `safe_rmtree`, `safe_write_text`.
* Ngữ nghĩa: `PermissionError` → warning + `sleep(0.5)` + retry 2 lần → `locked=True` kèm message "File is locked by another process (is Minecraft still running?)". `FileNotFoundError` → coi là thành công `skipped=True` (khi `missing_ok`). `OSError` khác → fail ngay, không retry.
* Retry ngắn có backoff cho rename/delete là chấp nhận được; im lặng bỏ qua lỗi thì không. Muốn fail cứng thì gọi `.unwrap()` → `FileOpError(OSError)`.
* Frontend: disable nút **Play/Start** khi instance đang busy (`InstanceCard.tsx` — dẫn xuất từ `tasks` trong Zustand store); mọi mutation trên instance phải set/clear cờ busy này.
* Clone instance: **copy vật lý thật** (`safe_copytree` với `symlinks=False`), không symlink/hardlink. Copy chọn lọc bằng `ignore=shutil.ignore_patterns(...)`.

---

## 4. RULE 4 — Sidecar Packaging (Nuitka)

* Công cụ: **Nuitka**, chế độ **`--standalone` (thư mục)** — **KHÔNG dùng `--onefile`** (tránh false-positive antivirus + startup chậm do giải nén).
* Lệnh build tham chiếu: `lenh_builnuitka.txt` (output `dist_sidecar/`).
* Layout khi release: `<app>/binaries/sidecar/phantomx-sidecar.exe` (Rust dò theo thứ tự này, xem `app/src-tauri/src/sidecar.rs`).
* Antivirus scan lần đầu có thể đẩy boot lên 8–10s → sidecar phải **bind port + in `PHANTOMX_READY` trước**, import thư viện nặng sau; timeout handshake phía Rust nên là **15s**.

---

## 5. Hợp đồng API đã verify (tin file này, không tin `Update.md`)

* Auth header: **`X-PhantomX-Token: <token>`** (chấp nhận thêm `Authorization: Bearer <token>` và `?token=` cho `EventSource`). Sai/thiếu token → **403 JSON** `{"detail": ...}`.
* Public paths: `/health`, `/api/docs`, `/api/redoc`, `/openapi.json`, `/api/openapi.json`.
* Routes hiện có (đã verify trong codebase sidecar):
  - **Health & Info**: `GET /health` · `GET /api/settings/info`
  - **Events & Tasks (SSE)**: `GET /api/events` (debug) · `GET /api/events/{task_id}` (SSE stream) · `GET /api/tasks` · `DELETE /api/tasks/{task_id}/cancel`
  - **Minecraft & Runtimes**: `GET /api/minecraft/versions` · `GET /api/minecraft/loaders/{loader}/{mc_version}` · `GET /api/minecraft/java`
  - **Instances**: `GET /api/instances` · `POST /api/instances/create` · `GET /api/instances/{name}` · `POST /api/instances/{name}/install` · `POST /api/instances/{name}/launch` · `POST /api/instances/{name}/stop` · `DELETE /api/instances/{name}` · `POST /api/instances/{name}/clone` · `PATCH /api/instances/{name}` · `POST /api/instances/{name}/open-folder`
  - **Settings**: `GET /api/settings` · `PUT /api/settings`
* SSE frames: `progress` · `log` · `heartbeat` (mỗi 5s khi queue rỗng) · `complete` (terminal, stream đóng ngay sau đó).
  Task bị cancel kết thúc bằng `complete{success:false, result:{cancelled:true}}` — frontend phải hiện "Cancelled", **không** hiện toast lỗi.
* CORS origins: `http://localhost:1420` (vite dev) + `http://127.0.0.1:1420` + `tauri://localhost` + `http://tauri.localhost` + `https://tauri.localhost`.

---

## 6. Bẫy đã biết (đừng đạp lại)

* `sse-starlette` expand dict thành `ServerSentEvent(**data)` → payload phải wrap `{"data": json.dumps(payload)}`, nếu không client nhận 200 + 0 event, im lặng.
* Starlette `add_middleware` chèn ở index 0 → **middleware add sau cùng là ngoài cùng**: token middleware add trước, `CORSMiddleware` add sau, ngược lại preflight `OPTIONS` sẽ 500.
* `raise HTTPException` trong `@app.middleware("http")` → 500. Phải `return JSONResponse(...)`.
* Return annotation của FastAPI đóng vai response_model → annotate sai kiểu (thiếu field) sẽ ValidationError → 500. Dùng `Dict[str, Any]` khi body động.
* `scr/core.py` gọi `logger.remove()` lúc import → xoá sink loguru của sidecar; `core_bridge.py` phải gọi lại `configure_logging()` sau khi import core.
* Rust `Drop` guard chỉ kill sidecar khi thoát graceful. `taskkill /F` hoặc crash parent → `python -m sidecar.main` mồ côi, giữ port. Cần Windows Job Object mới teardown vô điều kiện.
* `EventSource` **không** nhận SSE comment → ping mặc định của `sse-starlette` là vô hình với client. Bắt buộc dùng frame `heartbeat` dạng data thật (`api/events.py`).
* `bus.unsubscribe()` **xoá hẳn queue** trong `finally` của SSE handler → client reconnect giữa task sẽ mất event đã buffer (`subscribe()` tạo queue mới on-demand nên không crash). Chưa cần sửa, nhưng đừng dựa vào reconnect để replay.
* Cancel là **cooperative**: worker chỉ dừng ở `check_cancelled()` gần nhất. Mọi vòng lặp dài (download từng file, copy từng mod) phải gọi `ctx.check_cancelled()` mỗi vòng, nếu không nút Cancel sẽ "im lặng".
* Frontend không được tự set `running: false` khi bấm Cancel — chỉ set `cancelling: true`, đợi frame `complete`. Tắt sớm sẽ mở lại nút Play khi worker vẫn đang ghi file.

---

## 7. Trạng thái tuân thủ (Sprint 0 hoàn tất — 2026-09-02)

| Rule | Trạng thái | Bằng chứng / còn lại |
| --- | --- | --- |
| 1 — task_id + SSE | 🟢 đủ | Backend: `bus.py` · `services/tasks.py` (`TaskCancelled`, `check_cancelled`, `request_cancel`) · `api/tasks.py` (`GET /api/tasks`, `DELETE /api/tasks/{id}/cancel`) · `api/events.py` heartbeat 5s. Frontend: `lib/sse.ts` watchdog 10s → `onError`, `types.ts` `TaskHeartbeatEvent`, `api.ts cancelTask()`, store `cancelTask` + cờ `cancelling`, nút **Cancel Task** ở `TaskConsole.tsx`. Verify: 20/20 test end-to-end qua ASGI |
| 2 — Portable mode | 🟢 đủ | `sidecar/utils/path_resolver.py` là nguồn duy nhất; `logging_config.get_base_dir()` và `scr/core.py:BASE_DIR` đều delegate (có fallback cho legacy chạy độc lập). Verify: 12/12 test (default / portable.txt / `PHANTOMX_DATA_DIR`) |
| 3 — File locking | 🟢 backend đủ | `sidecar/utils/file_ops.py` (retry + `FileOpResult`); Verify: 27/27 test kể cả file bị lock thật trên Windows (`WinError 32` → `locked=True`, 3 attempts). Frontend đã disable Play khi busy (`InstanceCard.tsx:80`). **Còn lại**: các endpoint hiện có trong `api/instances.py` chưa được refactor sang `file_ops` (sẽ làm cùng Sprint 1) |
| 4 — Nuitka standalone | 🟡 gần đủ | `lenh_builnuitka.txt` đã `--standalone`, không `--onefile`; `HANDSHAKE_TIMEOUT_SECS = 15` ở `app/src-tauri/src/sidecar.rs`. **Còn lại**: chưa wire `dist_sidecar/` vào `tauri.conf.json` (`externalBin`/`resources`) |
| Bảo mật / Git | 🟢 đủ | `.gitignore` ở root, verify bằng `git check-ignore` trên repo tạm: 25/25 path đúng (`.env`, `*.pem`, `secrets.json`, `PhantomXData/`, `portable.txt`, `dist_sidecar/`, `.claude/settings.local.json`, …) |
