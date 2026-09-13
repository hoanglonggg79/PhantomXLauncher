# Sprint 4 Implementation Plan: UI Overhaul, Diagnostics, Discord RPC & Audio

Chuyển đổi và hoàn thiện **Sprint 4** cho PhantomX Launcher theo lộ trình [Update.md](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/Update.md), tuân thủ [GLOBAL_CONSTANTS.md](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/GLOBAL_CONSTANTS.md) (4 Quy tắc bất biến), [AGENT.md](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/AGENT.md) và `.gitignore`. Phiên bản giữ nguyên **1.2.0** (không bump version).

---

## User Review Required

> [!IMPORTANT]
> **Giữ nguyên Version 1.2.0**: Tuyệt đối không thay đổi chuỗi phiên bản trong mã nguồn (`Update.md` quy định giữ nguyên `1.2.0`).
> **Bảo mật Discord RPC**: Frontend chỉ gửi trạng thái logic trừu tượng (`idle`, `marketplace`, `in_game`, tên instance, loader). Mọi Asset ID Discord (`loader_fabric`, `badge_supporter`, `logo_phantomx`, App ID `1526783238406672475`) và thư viện `pypresence` được đóng gói hoàn toàn bên trong Python Sidecar.
> **Autoplay Policy của Webview**: Trình duyệt Webview có thể chặn phát nhạc tự động nếu chưa có tương tác chuột/bàn phím từ người dùng. Launcher sẽ ghi nhận trạng thái mute/unmute vào config, mặc định âm lượng 70%, và bắt đầu phát nhạc ngay khi người dùng tương tác hoặc nhấn nút bật nhạc.

---

## Proposed Changes

### Component 1: Desktop Shell (Tauri 2 / Rust) & Python Sidecar Lifecycle

Xử lý triệt để bài toán tiến trình mồ côi (Orphan Process) khi người dùng đóng cửa sổ hoặc app crash.

#### [MODIFY] [lib.rs](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/app/src-tauri/src/lib.rs)
- Trong `close_launcher`: lấy `State<SidecarState>` và chủ động gọi hàm terminate child process.
- Đăng ký hook vòng đời ứng dụng Tauri: bắt `RunEvent::Exit` và `RunEvent::ExitRequested` hoặc `WindowEvent::CloseRequested` để đảm bảo khi cửa sổ Tauri bị đóng ở bất kỳ đâu (nút X trên thanh tiêu đề, phím tắt Alt+F4, hay menu hệ thống), tiến trình con Python Sidecar sẽ bị ngắt ngay lập tức.

#### [MODIFY] [sidecar.rs](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/app/src-tauri/src/sidecar.rs)
- Bổ sung helper `SidecarState::kill_child(&self)` để tái sử dụng trong các lệnh đóng hoặc hook sự kiện.

#### [MODIFY] [main.py](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/sidecar/main.py)
- Triển khai **Parent Process Watchdog** (Giải pháp 2 - Cơ chế tự ngắt phía Sidecar):
  - Khởi động một daemon thread kiểm tra tiến trình cha định kỳ 2.5 giây.
  - Lúc Sidecar khởi động: lấy `parent_pid = os.getppid()` và lưu lại tên executable của cha (`parent_name = psutil.Process(parent_pid).name().lower()`, ví dụ `phantomx.exe` hoặc `app.exe`).
  - Kiểm tra an toàn chống **PID Recycling** trên Windows: mỗi chu kỳ 2.5s, không chỉ kiểm tra `psutil.pid_exists(parent_pid)` mà còn kiểm tra `psutil.Process(parent_pid).name().lower() == parent_name`.
  - Nếu cha không còn tồn tại hoặc tên executable bị thay đổi (PID bị tái sử dụng cho tiến trình khác) $\rightarrow$ ghi log và thoát ngay lập tức bằng `os._exit(0)`.
  - Hỗ trợ chế độ lập trình viên: nếu Sidecar được chạy trực tiếp từ terminal (parent là `cmd.exe`, `powershell.exe`, `code.exe`, hoặc biến môi trường `PHANTOMX_DEV_MODE=1`) thì bỏ qua cơ chế tự ngắt để dễ debug.

---

### Component 2: Diagnostics & System Repair Backend (`sidecar/`)

#### [NEW] [repair.py](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/sidecar/services/repair.py)
- **SHA-1 Integrity Hash Verification**:
  - Chạy background task qua `start_task()`, phát SSE progress (`progress`, `log`, `complete`) theo Rule 1.
  - Sử dụng `ThreadPoolExecutor(max_workers=6)` để tính hash bất đồng bộ mà không nghẽn ổ đĩa SSD hay đóng băng FastAPI event loop.
  - **Tối ưu hóa phạm vi kiểm tra**:
    1. Kiểm tra version manifest & client JAR (`versions/<mc_ver>/<mc_ver>.jar`). So sánh SHA-1 với manifest của Mojang.
    2. Kiểm tra thư viện (`libraries/**/*.jar`): duyệt danh sách `libraries` trong file version JSON, so sánh SHA-1 từng file `.jar`.
    3. Kiểm tra Assets: thay vì hash hàng nghìn file ảnh/âm thanh trong `assets/`, chỉ hash file index (`assets/indexes/<mc_ver>.json`) và đối chiếu số lượng/kích thước trong `assets/objects/`. Giảm thời gian quét từ vài phút xuống vài giây.
    4. Xây dựng hàng đợi tải xuống (`download_queue`): chỉ tải lại đúng các file bị thiếu hoặc sai SHA-1, không tải lại toàn bộ game.
- **Crash Log Analyzer (Quy tắc 80/20 Regex Pattern Matching)**:
  - Hàm `analyze_latest_crash(instance_name: str) -> Dict[str, Any]`:
    - Tìm kiếm file log gần nhất: ưu tiên file mới nhất trong `<instance_dir>/crash-reports/crash-*.txt` (sắp xếp theo mtime), nếu không có thì đọc đuôi file `<instance_dir>/logs/latest.log`.
    - Quét 3 mẫu Regex cốt lõi:
      1. **Out of Memory (OOM)**: Regex `r"java\.lang\.OutOfMemoryError"` $\rightarrow$ Gợi ý người dùng tăng RAM cấp cho JVM trong Cài đặt.
      2. **Xung đột / Thiếu Mod**: Regex `r"Missing or unsupported mandatory dependencies:.*?needs ([\w\-\.]+)"` hoặc `r"net\.fabricmc\.loader\.impl\.FormattedException:.*?"` hoặc `r"Mod '(.*?)' requires.*?"` $\rightarrow$ Trích xuất tên mod bị thiếu/xung đột.
      3. **Sai phiên bản Java**: Regex `r"UnsupportedClassVersionError|has been compiled by a more recent version of the Java Runtime"` $\rightarrow$ Gợi ý chuyển sang Java 8 (MC $\le$ 1.16.5), Java 17 (MC 1.17 - 1.20.4), hoặc Java 21 (MC $\ge$ 1.20.5).
      4. **Lỗi khác (General Crash)**: Hiển thị đoạn snippet báo lỗi, đường dẫn file log chi tiết, nút "Copy Log" và khuyến nghị gửi báo cáo lên Discord.
- **Clean Cache & Reset Options**:
  - `reset_options(instance_name: str)`: Sao lưu và khôi phục `options.txt` về mặc định (giải quyết các lỗi liên quan đến driver màn hình/độ phân giải).
  - `clean_cache()`: Dọn dẹp thư mục tạm `.tmp`, cache tải xuống và log cũ.

#### [NEW] [repair.py](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/sidecar/api/repair.py)
Định nghĩa router `/api/repair` phục vụ Frontend:
- `POST /api/repair/{name}/verify-integrity`: Trả về `202 {"task_id": "...", ...}`.
- `GET /api/repair/{name}/analyze-crash`: Trả về kết quả phân tích lỗi crash gần nhất.
- `POST /api/repair/{name}/reset-options`: Đặt lại cài đặt `options.txt`.
- `POST /api/repair/clean-cache`: Dọn dẹp cache toàn cục.

#### [MODIFY] [app.py](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/sidecar/app.py)
- Đăng ký `repair.router` với prefix `/api/repair`.

---

### Component 3: Discord Rich Presence (RPC) Backend (`sidecar/`)

#### [NEW] [discord_rpc.py](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/sidecar/services/discord_rpc.py)
- Tích hợp thư viện `pypresence` chạy trên background worker thread riêng biệt.
- Sử dụng Application ID: `1526783238406672475`.
- Rate Limiting: Đảm bảo khoảng cách giữa các lần cập nhật tối thiểu 15 giây trừ khi có sự thay đổi trạng thái đột ngột (Idle $\rightarrow$ In-Game).
- An toàn & Non-blocking: Bọc toàn bộ kết nối trong `try...except`, không để việc Discord tắt/chưa bật gây ảnh hưởng đến tiến trình khởi chạy game hoặc giao diện.
- **Trạng thái hiển thị (Discord Status Mapping)**:
  1. **Idle (Đang duyệt Launcher)**:
     - Details: `Browsing Launcher`
     - State: `v1.2.0 • Idle`
     - Large Image: `logo_phantomx`, Large Text: `PhantomX Launcher v1.2.0`
     - Buttons: `Get PhantomX` (Link GitHub Releases), `Join Discord` (`https://discord.gg/PECavu2q4w`)
  2. **Marketplace (Đang duyệt Mod)**:
     - Details: `Dạo quanh Marketplace`
     - State: `Đang tìm kiếm Mods`
     - Large Image: `logo_phantomx`, Large Text: `PhantomX Launcher`
  3. **In-Game (Đang chơi Minecraft)**:
     - Details: `Đang chơi Minecraft`
     - State: `Instance: <Tên_Instance>`
     - Large Image: `logo_phantomx`, Large Text: `Minecraft <Version> (<Loader>)`
     - Small Image: Phụ thuộc vào loader: `loader_fabric`, `loader_forge`, `loader_neoforge`, hoặc `mc_vanilla`.
     - Nếu là Supporter: Text hiển thị `PhantomX Supporter ❤` kèm badge.
     - Timestamps: Elapsed time tính từ lúc game bắt đầu khởi chạy.

#### [MODIFY] [system_diagnostics.py](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/sidecar/api/system_diagnostics.py)
- Thêm endpoint `POST /api/system/discord_rpc` nhận payload gọn gàng từ UI:
  `{ "status": "idle" | "marketplace" | "in_game", "instance_name"?: str, "loader"?: str, "mc_version"?: str, "is_supporter"?: bool }`.

#### [MODIFY] [instances.py](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/sidecar/services/instances.py)
- Tự động gọi cập nhật Discord RPC khi game bắt đầu chạy (`_launch`) và tự động chuyển về `idle` khi game tắt (`proc.wait()`).

---

### Component 4: Background Music Player & Theme Preparation (`sidecar/` + Frontend)

#### [NEW] [theme_audio.py](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/sidecar/services/theme_audio.py)
- Quản lý file nhạc nền tại `%LOCALAPPDATA%\PhantomXTeam\PhantomX\theme\theme.mp3` (hoặc thư mục Portable).
- Hàm `ensure_theme_audio()`: Kiểm tra sự tồn tại của `theme.mp3`. Nếu chưa có, tự động tải từ `https://github.com/hoanglonggg79/storage/releases/download/010/theme.mp3` vào thư mục theme.

#### [MODIFY] [system_diagnostics.py](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/sidecar/api/system_diagnostics.py)
- Endpoint `GET /api/system/theme/audio`: Phục vụ file âm thanh `theme.mp3` dưới dạng stream (`FileResponse`), cho phép trình duyệt HTML5 `<audio>` phát mượt mà không gặp giới hạn bảo mật cục bộ file:/// của Webview.
- Endpoint `POST /api/system/theme/prepare`: Kích hoạt tải trước file nhạc nếu chưa có.

#### [MODIFY] [core_service.py](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/sidecar/services/core_service.py) & [settings.py](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/sidecar/api/settings.py)
- Bổ sung cấu hình người dùng vào `config.json`:
  - `bg_music_enabled: bool` (mặc định `true`)
  - `bg_music_volume: float` (mặc định `0.7` ~ 70%)
  - `discord_rpc_enabled: bool` (mặc định `true`)

---

### Component 5: Cyberpunk Loading Screen (Splash Screen)

#### [MODIFY] [ConnectionGate.tsx](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/app/src/components/ConnectionGate.tsx)
- Thiết kế lại giao diện khởi động mang phong cách Cyberpunk Glassmorphism đỉnh cao:
  - Logo PhantomX tỏa sáng với hiệu ứng neon pulse ring.
  - Thanh trạng thái tiến trình thực tế (Real-time Progress Indicator) với các giai đoạn:
    - *Khởi tạo PhantomX Core & Sidecar Handshake...*
    - *Kết nối dịch vụ hệ thống...*
    - *Đồng bộ cấu hình & nạp danh sách Instances...*
    - *Khôi phục phiên Ely.by & Huy hiệu Supporter...*
    - *Chuẩn bị nhạc nền PhantomX Theme...*
    - *Sẵn sàng!*
  - Chuyển cảnh mềm mại (Fade-out transition 300ms) sang giao diện chính ngay khi nhận `PHANTOMX_READY` và nạp xong dữ liệu khởi động cơ bản (tuyệt đối không dùng delay giả 5s).

---

### Component 6: Advanced Repair & Crash Diagnostics UI (Frontend)

#### [NEW] [RepairDialog.tsx](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/app/src/components/instances/RepairDialog.tsx)
- Modal chẩn đoán và sửa chữa toàn diện cho Instance:
  - **Tab 1: Kiểm tra toàn vẹn (Integrity Verification)**:
    - Nút "Bắt đầu quét & sửa chữa".
    - Kết nối với tác vụ `POST /api/repair/{name}/verify-integrity`, hiển thị trực tiếp tiến độ SSE và log tải file.
  - **Tab 2: Phân tích lỗi Crash (Crash Analyzer)**:
    - Nút "Phân tích Crash Log gần nhất".
    - Tự động hiển thị Card chẩn đoán theo kết quả Regex (OOM / Mod conflict / Java mismatch / Unknown).
    - Thẻ khuyến nghị hành động nhanh (ví dụ: nút "Đổi RAM trong Cài đặt", "Đổi phiên bản Java").
    - Nút **"Copy Log"** nhỏ gọn, thiết kế tinh tế để người dùng bấm copy toàn bộ chẩn đoán + log snippet vào clipboard.
    - Nút "Báo cáo lỗi qua Discord" (mở `ReportBugDialog` hoặc link Discord).
  - **Tab 3: Đặt lại & Dọn dẹp**:
    - Nút "Reset options.txt": Khôi phục cài đặt hiển thị/đồ họa.
    - Nút "Dọn dẹp cache": Xóa sạch các file tạm và log rác.

#### [NEW] [BackgroundMusicPlayer.tsx](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/app/src/components/layout/BackgroundMusicPlayer.tsx)
- Widget âm nhạc gọn gàng đặt tại Header hoặc Sidebar góc trái:
  - Nút Mute / Unmute với hiệu ứng sóng âm nhạc (Sound wave animation).
  - Tự động phát khi người dùng tương tác với launcher nếu autoplay bị chặn ban đầu.
  - Đồng bộ âm lượng 70% mặc định, lưu trạng thái bật/tắt vào settings.

#### [MODIFY] [SettingsPanel.tsx](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/app/src/components/settings/SettingsPanel.tsx)
- Thêm mục **Âm thanh & Discord**:
  - Slider điều chỉnh âm lượng nhạc nền (0% - 100%).
  - Switch bật/tắt phát nhạc nền tự động.
  - Switch bật/tắt Discord Rich Presence.

#### [MODIFY] [InstanceCard.tsx](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/app/src/components/instances/InstanceCard.tsx)
- Gắn `RepairDialog` vào nút Repair và menu ba chấm (`...`) của Instance Card.
- Khi một instance bị crash (nhận mã lỗi thoát `exit_code != 0`), hiển thị toast cảnh báo kèm nút tắt "Xem phân tích lỗi" mở ngay tab Crash Analyzer của `RepairDialog`.

#### [MODIFY] [Header.tsx](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/app/src/components/layout/Header.tsx)
- Tích hợp `BackgroundMusicPlayer` vào thanh điều hướng Header cạnh AccountPill.

#### [MODIFY] [app-store.ts](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/app/src/store/app-store.ts) & [api.ts](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/app/src/lib/api.ts) & [types.ts](file:///c:/Users/Long/Desktop/PY/MinecraftLauncher/app/src/lib/types.ts)
- Bổ sung typed API clients: `verifyIntegrity`, `analyzeCrash`, `resetOptions`, `cleanCache`, `updateDiscordRpc`, `getThemeAudioUrl`.
- Bổ sung state điều khiển modal Repair & Audio player.

---

## Verification Plan

### Automated / Syntax & Compilation Checks
1. **Sidecar Python verification**:
   - Chạy lệnh kiểm tra cú pháp và import:
     ```powershell
     python -m py_compile sidecar/main.py sidecar/services/repair.py sidecar/services/discord_rpc.py sidecar/services/theme_audio.py sidecar/api/repair.py
     ```
2. **Frontend TypeCheck & Lint**:
   - Kiểm tra build và TypeScript types:
     ```powershell
     cd app; npm run build
     ```
3. **Rust Compilation Check**:
   - Kiểm tra mã Rust Tauri:
     ```powershell
     cd app/src-tauri; cargo check
     ```

### Manual Verification
1. **Kiểm tra Parent Process Watchdog & Exit Handling**:
   - Khởi động app bằng `npm run tauri dev`.
   - Kiểm tra Task Manager xem `phantomx-sidecar` hoặc tiến trình Python chạy kèm.
   - Bấm nút X tắt cửa sổ Tauri $\rightarrow$ Kiểm tra Task Manager đảm bảo cả Rust và Python đều đã dừng hoàn toàn (không còn tiến trình mồ côi).
2. **Kiểm tra Crash Log Analyzer**:
   - Thử nghiệm phân tích crash log (mô phỏng log có OutOfMemory, Missing fabric dependency, và Java version mismatch).
   - Kiểm tra nút "Copy Log" copy thành công nội dung vào Clipboard.
3. **Kiểm tra SHA-1 Integrity Verification**:
   - Bấm kiểm tra toàn vẹn trên một instance thử nghiệm.
   - Quan sát SSE task progress, đảm bảo thời gian chạy chỉ mất vài giây thay vì vài phút nhờ cơ chế hash thông minh index + client jar + libraries.
4. **Kiểm tra Trình phát nhạc nền**:
   - Kiểm tra file `theme.mp3` được tải về `%LOCALAPPDATA%\PhantomXTeam\PhantomX\theme\`.
   - Kiểm tra nghe nhạc phát ở mức âm lượng 70%, bấm Mute/Unmute trên Header, chỉnh thanh trượt volume trong Settings.
5. **Kiểm tra Discord Rich Presence**:
   - Bật Discord trên máy tính.
   - Mở Launcher $\rightarrow$ Profile Discord hiện trạng thái "Browsing Launcher".
   - Vào tab Chợ Mod $\rightarrow$ Profile Discord hiện trạng thái "Dạo quanh Marketplace".
   - Khởi chạy game $\rightarrow$ Profile Discord hiện "Đang chơi Minecraft" kèm tên instance, loader và thời gian chơi.
6. **Kiểm tra Cyberpunk Loading Screen**:
   - Quan sát màn hình Splash phong cách Cyberpunk khi mở ứng dụng, các dòng trạng thái thực nạp mượt mà và fade-out 300ms vào màn hình chính.
