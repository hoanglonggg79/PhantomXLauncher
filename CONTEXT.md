# 🧠 CONTEXT: PhantomX Launcher Migration & Technical Overview

**Cập nhật:** Tháng 09/2026  
**Dự án:** Chuyển đổi toàn diện PhantomX Minecraft Launcher từ **PyQt6 (Legacy `scr/`)** sang mô hình **Tauri 2 (Rust) + Python FastAPI Sidecar (`sidecar/`) + React 19 / TypeScript (`app/src/`)**.  
**Trạng thái:** ✅ **Sprint 0 Hoàn tất** (Nền tảng Shell, Handshake, Bảo mật Token, Async SSE Tasks, File Locking Safe Ops, Path Resolver Portable). Core UI (Instance Grid, Create Instance, Task Console, Settings, About) đang hoạt động kết nối trơn tru với Sidecar.

> ⚠️ **LƯU Ý:** Đọc [GLOBAL_CONSTANTS.md](GLOBAL_CONSTANTS.md) để nắm **4 Quy Tắc Bất Biến** và **Hợp đồng API chuẩn**.

---

## 🏗️ 1. Kiến trúc Hệ thống 3 Tầng (3-Tier Architecture)

```mermaid
graph TD
    subgraph UI ["Frontend (app/src/ - React 19 + Vite 7 + TS 5.8)"]
        ReactApp["React UI (Tailwind v4 + shadcn/Radix)"]
        ZStore["Zustand Store (app-store.ts)"]
        HTTPClient["Axios Client (lib/api.ts)"]
        SSEListener["SSE Stream Listener (lib/sse.ts)"]
    end

    subgraph Shell ["Desktop Shell (app/src-tauri/ - Tauri 2 / Rust)"]
        TauriCore["Tauri 2 Core"]
        Spawner["Sidecar Spawner (tokio timeout 15s)"]
        TauriState["Tauri State (Port, Token, Child Process)"]
    end

    subgraph Backend ["Core Backend (sidecar/ - FastAPI Python)"]
        FastAPIApp["FastAPI (127.0.0.1:dynamic_port)"]
        TokenMW["Auth Middleware (X-PhantomX-Token)"]
        EventBus["Thread-Safe EventBus (asyncio.Queue)"]
        TaskMgr["Task Manager (Background Threads + Cancel)"]
        FileOps["Safe FileOps (Windows Locking Safe)"]
        PathRes["Path Resolver (Portable / AppData)"]
        CoreBridge["Core Bridge (scr/core.py - Qt decoupled)"]
    end

    subgraph MinecraftClient ["Game Process"]
        MC["Minecraft Client (Java Runtime)"]
    end

    TauriCore -->|1. Spawns & Handshake| Spawner
    Spawner -->|PHANTOMX_READY:port:token| TauriState
    TauriCore -->|2. invoke('get_sidecar_info')| ReactApp
    ReactApp --> ZStore
    ZStore --> HTTPClient
    ZStore --> SSEListener
    HTTPClient -->|3. REST Requests + Token| FastAPIApp
    SSEListener -->|4. GET /api/events/{task_id}| FastAPIApp
    FastAPIApp --> TokenMW
    TokenMW --> TaskMgr
    TaskMgr --> EventBus
    EventBus -->|SSE Events: progress / log / complete| SSEListener
    TaskMgr --> CoreBridge
    CoreBridge -->|Launch Command| MC
    TaskMgr --> FileOps
    TaskMgr --> PathRes
```

### Luồng khởi động (Startup Flow)
1. **Tauri Shell khởi chạy:** Rust spawner (`sidecar.rs`) khởi động tiến trình Python Sidecar (`python -m sidecar.main`).
2. **Dynamic Port & Handshake:** Python tìm một port rảnh ngẫu nhiên trên `127.0.0.1`, sinh token bảo mật ngẫu nhiên, và in duy nhất 1 dòng ra **stdout**:  
   `PHANTOMX_READY:<port>:<token>` (kèm `flush=True`).
3. **Rust Handshake Capture:** Rust đọc stdout với timeout **15 giây** (chống nghẽn do Antivirus scan), lưu port và token vào Tauri `State`, đồng thời đóng pipe stdout.
4. **Frontend Handshake:** React UI khởi chạy, hiển thị `ConnectionGate`, gọi command Tauri `get_sidecar_info` để lấy `port` và `token`.
5. **Khởi tạo kết nối:** `lib/api.ts` thiết lập Axios instance với header `X-PhantomX-Token`, kiểm tra `GET /health`, nạp danh sách instance, settings và chuyển UI sang trạng thái `ready`.

---

## 📂 2. Cấu trúc Cây Thư mục & Vai trò

```text
MinecraftLauncher/
├── CLAUDE.md                   # Tóm tắt nhanh context và 4 quy tắc cho AI session
├── CONTEXT.md                  # Tài liệu ngữ cảnh kỹ thuật chi tiết (file này)
├── GLOBAL_CONSTANTS.md         # Nguồn chân lý (Single source of truth) về rules & API
├── Update.md                   # Roadmap nâng cấp, ma trận tính năng & log quyết định
├── requirements.txt            # Python dependencies (sidecar + legacy core)
│
├── app/                        # [TẦNG 1 & 2] Frontend React + Desktop Shell Tauri 2
│   ├── src/                    # Frontend React 19 + TypeScript + Vite 7
│   │   ├── components/         # UI Components
│   │   │   ├── about/          # AboutPanel.tsx (thông tin launcher, version, credits)
│   │   │   ├── console/        # TaskConsole.tsx (SSE log terminal + Cancel Task button)
│   │   │   ├── instances/      # InstanceGrid, InstanceCard, CreateInstanceDialog
│   │   │   ├── layout/         # Header, Sidebar, Nav items
│   │   │   ├── settings/       # SettingsPanel.tsx (RAM, Java, launcher config)
│   │   │   ├── ui/             # Radix / shadcn primitives (Button, Dialog, Toast, Select...)
│   │   │   ├── ConnectionGate.tsx # Màn hình chờ kết nối handshake với Sidecar
│   │   │   └── NoticeToast.tsx    # Toast thông báo toàn cục
│   │   ├── lib/
│   │   │   ├── api.ts          # Axios client, toàn bộ hàm REST API gọi sang Sidecar
│   │   │   ├── sse.ts          # SSE Event reader + Watchdog (10s timeout)
│   │   │   ├── types.ts        # TypeScript interfaces (Instance, Task, Event, Settings...)
│   │   │   └── utils.ts        # cn helper, formatters
│   │   ├── store/
│   │   │   └── app-store.ts    # Zustand 5 App State (instances, active tasks, screen, settings)
│   │   ├── App.tsx             # Root layout & tab router
│   │   └── index.css           # Tailwind v4 styles, Dark Void theme & Glassmorphism tokens
│   │
│   └── src-tauri/              # Desktop Shell Tauri 2 (Rust)
│       ├── src/
│       │   ├── lib.rs          # Module declarations & Tauri builder setup
│       │   ├── main.rs         # Tauri application entry point
│       │   └── sidecar.rs      # Quản lý vòng đời Sidecar, handshake parse, drop kill
│       ├── Cargo.toml          # Rust dependencies (tauri, tokio, serde...)
│       └── tauri.conf.json     # Cấu hình cửa sổ Tauri, permissions & bundle
│
├── sidecar/                    # [TẦNG 3] Backend FastAPI (Python)
│   ├── api/                    # FastAPI Routers
│   │   ├── events.py           # SSE endpoint: GET /api/events/{task_id}
│   │   ├── instances.py        # CRUD instance, clone, delete, update, install, launch, stop
│   │   ├── minecraft.py        # Query Minecraft versions, loader versions, Java detection
│   │   ├── settings.py         # GET/PUT settings, system info
│   │   └── tasks.py            # GET /api/tasks, DELETE /api/tasks/{task_id}/cancel
│   ├── services/               # Core Business Logic
│   │   ├── bus.py              # Thread-safe EventBus (asyncio.Queue) phát SSE events
│   │   ├── core_service.py     # Singleton bọc MinecraftManager từ core_bridge
│   │   ├── instances.py        # Instance operations (create, clone, safe delete, launch, log parsing)
│   │   └── tasks.py            # Task worker runner, cancel token, context management
│   ├── utils/                  # Tiện ích nền tảng bất biến
│   │   ├── file_ops.py         # Thao tác file an toàn cho Windows File Locking (retry backoff)
│   │   └── path_resolver.py    # Phân giải đường dẫn Portable mode vs %LOCALAPPDATA%
│   ├── app.py                  # FastAPI factory, verify_token middleware, CORS
│   ├── core_bridge.py          # Bridge nhập scr/core.py (Qt decoupled)
│   ├── logging_config.py       # Cấu hình Loguru ghi log ra file và stderr (không đụng stdout)
│   ├── main.py                 # Sidecar entrypoint, dynamic port allocation, in handshake
│   └── session.py              # Lưu trữ runtime token trong bộ nhớ tiến trình Sidecar
│
└── scr/                        # [LEGACY] Mã nguồn PyQt6 cũ (Chỉ đọc tham khảo logic)
    ├── core.py                 # Core business logic cũ (đã được bọc an toàn không cần Qt)
    ├── main_window.py          # Legacy PyQt6 MainWindow
    ├── ui_tabs.py              # Legacy PyQt6 Tabs (InstanceTab, ModTab, MarketplaceTab...)
    ├── ui_modpack.py           # Legacy Modpack Installer Worker
    └── ui_repair.py            # Legacy Diagnostic & Repair Worker
```

---

## 🔒 3. Bảo mật & Giao thức Giao tiếp

1. **Authentication Token (`X-PhantomX-Token`):**
   - Mỗi lần khởi động, Sidecar tự sinh token bí mật bằng `secrets.token_urlsafe(32)`.
   - Token chỉ được chia sẻ qua kênh stdout lúc bắt tay duy nhất với Rust shell.
   - Frontend gửi kèm header `X-PhantomX-Token: <token>` trong mọi REST request.
   - Endpoint SSE nhận token qua query string `?token=<token>` (do chuẩn HTML5 `EventSource` không cho đặt custom header).
   - Middleware `verify_token` trong `sidecar/app.py` kiểm tra bằng `secrets.compare_digest`. Trả về `403 JSON` nếu không hợp lệ.

2. **CORS & Bind Address:**
   - Sidecar **chỉ bind duy nhất vào `127.0.0.1`**, tuyệt đối không bind `0.0.0.0`.
   - Middleware `CORSMiddleware` được đăng ký ngoài cùng để xử lý chuẩn xác preflight request `OPTIONS` từ Webview.

3. **Giao tiếp Asynchronous SSE & Cancel Task:**
   - Mọi tác vụ tốn thời gian (tải game, verify file, clone instance, cài loader) chạy trên background worker qua `start_task()`, trả về ngay `202 {"task_id": "..."}`.
   - Frontend lắng nghe SSE stream tại `/api/events/{task_id}`.
   - Luôn có frame **`heartbeat`** mỗi 5s (phía server) và **watchdog timeout 10s** (phía client).
   - Người dùng có thể bấm nút **"Cancel Task"** bất kỳ lúc nào để huỷ tác vụ an toàn.

---

## 🛡️ 4. Xử lý File & Hệ Thống Tệp Trên Windows

1. **Windows File Locking (`sidecar/utils/file_ops.py`):**
   - Mọi thao tác tệp (`safe_delete`, `safe_rename`, `safe_copy`, `safe_copytree`, `safe_rmtree`, `safe_write_text`) tự động xử lý `PermissionError` (WinError 5 / WinError 32) với cơ chế retry 2 lần (backoff 0.5s) trước khi trả về `FileOpResult(ok=False, locked=True)`.
   - Không làm sập tiến trình, trả thông báo rõ ràng cho UI nếu file đang bị Minecraft hoặc Defender khóa.

2. **Portable Mode & Data Directory (`sidecar/utils/path_resolver.py`):**
   - Nếu có file `portable.txt` nằm cạnh file thực thi $\to$ Lưu trữ dữ liệu tại `<exe_dir>/PhantomXData/`.
   - Mặc định $\to$ Lưu trữ tại `%LOCALAPPDATA%\PhantomXTeam\PhantomX\`.
   - Biến môi trường `$PHANTOMX_DATA_DIR` dùng để override tuyệt đối khi test/CI.
   - **Tuyệt đối không ghi file rác/log cạnh `.exe`** ở chế độ standard mode.

---

## 💻 5. Lệnh Phát triển & Kiểm thử

```bash
# 1. Chạy Frontend độc lập (Vite Dev Server - Port 1420)
cd app && npm run dev

# 2. Chạy toàn bộ ứng dụng Desktop (Tauri Shell + Tự spawn Sidecar)
cd app && npm run tauri dev

# 3. Chạy Sidecar độc lập để debug / test API
python -m sidecar.main

# 4. Kiểm tra mã nguồn Rust
cd app/src-tauri && cargo check
```

---

## 🧭 6. Kế hoạch Phát triển Tiếp theo

Tham khảo chi tiết tại [Update.md](Update.md):
- **Sprint 1:** Hoàn thiện giao diện Quản lý Mod cục bộ (Mod Manager Dialog) và kết nối menu hành động Instance (Clone dialog, Rename, Delete confirmation, Open folder).
- **Sprint 2:** Java Runtime Downloader tự động (Adoptium API) & Quản lý nhiều bản Java JRE.
- **Sprint 3:** Tích hợp Modrinth / CurseForge Marketplace & Trình cài đặt Modpack (.mrpack / .zip).
- **Sprint 4:** Công cụ chẩn đoán Crash Report Regex, Discord Rich Presence (RPC) & Background Music Player.
