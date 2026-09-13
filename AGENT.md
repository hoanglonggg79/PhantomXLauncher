# CLAUDE.md — PhantomX Launcher

**Đọc [GLOBAL_CONSTANTS.md](GLOBAL_CONSTANTS.md) (Nguồn chân lý) và [CONTEXT.md](CONTEXT.md) (Chi tiết kiến trúc & Context) trước khi code.** File này là bản tóm tắt nhanh được auto-load mỗi phiên làm việc.

## Kiến trúc

`app/src/` React 19 + Vite + Tailwind v4 + shadcn/Radix + Zustand ⇄ REST/SSE ⇄ `sidecar/` FastAPI (Python) · `app/src-tauri/` Tauri 2 (Rust) chỉ là shell: spawn sidecar, đọc handshake `PHANTOMX_READY:<port>:<token>` từ stdout, giữ port+token trong Tauri State. `scr/` là UI PyQt6 legacy — **chỉ đọc tham khảo**, `core.py` được reuse qua `sidecar/core_bridge.py`.

## 4 QUY TẮC BẤT BIẾN

1. **Async & SSE** — Mọi tác vụ dài (download, verify, install, tải Java) chạy background thread qua `start_task()`, trả `202 {task_id}`, stream qua SSE `/api/events/{task_id}`, và **luôn** phát frame `complete` (kể cả khi fail). Frontend phải có heartbeat 5s + nút "Cancel Task" — không bao giờ để spinner quay vô hạn.
2. **Pathing & Portable** — Có `portable.txt` cạnh executable → relative path; không có → `%LOCALAPPDATA%\PhantomXTeam\PhantomX\`. **Không bao giờ ghi file cạnh `.exe`.** Lấy path từ helper duy nhất, không tự ghép.
3. **Windows File Locking** — Mọi `rename`/`remove`/`replace`/`rmtree`/`copy` trong Python phải `try...except (PermissionError, FileNotFoundError)` và trả lỗi có nghĩa cho UI. Frontend disable nút Play khi `isInstanceBusy === true`. Clone instance = copy vật lý, không symlink.
4. **Packaging** — Nuitka **`--standalone` (thư mục)**, không `--onefile`. Sidecar bind port + in handshake TRƯỚC khi import thư viện nặng; Rust timeout handshake 15s.

## Không được làm

* `print()` ra stdout trong sidecar (stdout dành riêng cho handshake) — log qua loguru (stderr + file).
* Trả về SSE payload trần: `sse-starlette` cần `{"data": json.dumps(payload)}`.
* `raise HTTPException` trong `@app.middleware("http")` → dùng `return JSONResponse(...)`.
* Đăng ký `CORSMiddleware` trước token middleware (thứ tự ngược → preflight 500).
* Tin `Update.md`/`CONTEXT.md` về hợp đồng API: auth thật là header **`X-PhantomX-Token`**, không phải `Authorization: Bearer`.

## Commands

```bash
cd app && npm run dev          # vite dev (port 1420)
cd app && npm run tauri dev    # full shell + auto-spawn sidecar
python -m sidecar.main         # chạy sidecar độc lập (in handshake ra stdout)
cd app/src-tauri && cargo check
```
