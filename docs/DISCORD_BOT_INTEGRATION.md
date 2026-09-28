# Hướng Dẫn Tích Hợp Discord Bot — PhantomX Supporter System

Tài liệu này mô tả cách hệ thống **PhantomX Supporter** vận hành giữa **Discord Bot** (chạy trên máy cá nhân hoặc VPS của team) và **Cloudflare Worker Serverless API 24/7**.

> **Kiến trúc hiện tại:** xác thực qua **redeem code** + **Cloudflare Worker / D1**. Cơ chế **mã hóa bất đối xứng (RSA signed token)** đã được **loại bỏ hoàn toàn** và không còn được hỗ trợ.

---

## 1. Thông Số Cấu Hình

- **API Endpoint:** `https://phantomx-supporter-api.hoanglonggg79.workers.dev`
- **Admin Secret Token:** đặt trong `.env` của bot qua biến `ADMIN_TOKEN`
- **D1 Database Binding:** `DB` (`phantomx-supporter-db`)

Các biến môi trường cần có trong `PTX_Bot/.env`:

| Biến | Mô tả |
| :--- | :--- |
| `DISCORD_TOKEN` | Token đăng nhập bot Discord |
| `CLIENT_ID` | Application ID (dùng khi deploy slash command) |
| `ADMIN_IDS` | Danh sách Discord ID được phép dùng lệnh admin, phân tách bằng dấu phẩy |
| `BUYER_ROLE_ID` | ID vai trò tri ân cấp cho người hỗ trợ |
| `WORKER_URL` | Base URL của Cloudflare Worker |
| `ADMIN_TOKEN` | Bearer token cho mọi endpoint `/admin/*` |

---

## 2. Các API Endpoint Phía Serverless

| Method | Endpoint | Quyền | Mục đích | Payload |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/admin/init-db` | Admin | Khởi tạo bảng D1 (chỉ cần gọi 1 lần đầu) | *None* |
| `POST` | `/admin/generate` | Admin | Sinh danh sách key tri ân `PX-xxxx` | `{ "tier": "supporter", "discord_id": "...", "count": 1 }` |
| `POST` | `/admin/lookup` | Admin | Tra cứu key (read-only, bot dùng để pre-check) | `{ "discord_id": "..." }` hoặc `{ "key_code": "...", "discord_id": "..." }` |
| `POST` | `/admin/reset-hwid`| Admin | Giải phóng ràng buộc phần cứng (Cooldown 4 ngày) | `{ "discord_id": "..." }` hoặc `{ "key_code": "...", "discord_id": "..." }` |
| `POST` | `/admin/revoke` | Admin | Khóa / thu hồi key | `{ "key_code": "PX-...", "reason": "Lý do" }` |
| `POST` | `/redeem` | Public | Launcher kích hoạt key & bind HWID | `{ "key_code": "...", "hwid": "...", "uuid": "..." }` |
| `POST` | `/verify` | Public | Launcher đồng bộ trạng thái online | `{ "key_code": "...", "hwid": "..." }` |

*Lưu ý: Tất cả các endpoint `/admin/*` bắt buộc phải truyền header:*

```http
Authorization: Bearer <ADMIN_TOKEN>
```

### 2.1 Điều kiện bắt buộc khi giải phóng thiết bị (Reset HWID)

Một yêu cầu reset chỉ được chấp nhận khi **tài khoản đã có Supporter Key trên D1**. Cụ thể, Worker kiểm tra:

1. **Có key** — tìm thấy key theo `discord_id` (hoặc theo `key_code` nếu được cung cấp). Không có → `404 { no_key: true }`.
2. **Đúng chủ sở hữu** — khi request có kèm `discord_id`, key phải thuộc về chính tài khoản đó. Sai → `403 { not_owner: true }`.
3. **Chưa bị thu hồi** — `is_blocked = 0`. Đã khóa → `403 { revoked: true }`.
4. **Đã từng kích hoạt** — `is_used = 1`. Key chưa từng kích hoạt thì chưa gắn thiết bị nào → `409 { not_activated: true }`.
5. **Ngoài cooldown** — ít nhất 4 ngày kể từ lần reset trước → nếu chưa đủ thì `429`.

Bot còn **pre-check qua `/admin/lookup`** trước khi hiện dialog xác nhận, để người dùng biết ngay mình chưa đủ điều kiện thay vì xác nhận rồi mới báo lỗi. Pre-check là best-effort: nếu Worker chưa được deploy endpoint này (trả về health JSON) hoặc lỗi mạng thì bot bỏ qua và để `/admin/reset-hwid` quyết định — tránh chặn nhầm người dùng hợp lệ.

> **Admin được bỏ qua ràng buộc chủ sở hữu:** khi admin dùng `/reset-hwid <key_code>`, bot không gửi kèm `discord_id` nên có thể hỗ trợ thủ công key của người khác. Các điều kiện còn lại (có key, chưa khóa, đã kích hoạt, cooldown) vẫn được áp dụng.

---

## 3. Hai Loại Mã Trong Hệ Thống

| Loại | Định dạng | Nơi sinh | Redeem tại panel | Cấp vai trò tri ân |
| :--- | :--- | :--- | :--- | :--- |
| **Mã thường** | `KEY-XXXXXXXX` | Bot — lệnh `/generatecode` | Có | Không (trao tay sau khi đã có giấy phép) |
| **Key tri ân** | `PX-XXXX-XXXX-XXXX` | Cloudflare D1 — lệnh `/genkey` | **Có** | **Có** |

### 3.1 Key tri ân `PX-` dùng được như code thường

Đây là điểm quan trọng nhất của thiết kế hiện tại: **key tri ân `PX-xxxx` redeem được y như một mã `KEY-xxxx` bình thường.**

- Khi admin chạy `/genkey`, bot gọi D1 sinh key rồi **tự động đăng ký key đó vào bảng `redeem_codes`** của bot.
- Người hỗ trợ chỉ cần bấm **Kích Hoạt Mã** trên panel và dán key `PX-...` là xong — bot cấp giấy phép và cho phép nhận vai trò tri ân.
- Kể cả khi key chưa từng được đăng ký trước (ví dụ key phát hành thủ công trên D1), luồng redeem vẫn **tự đăng ký tại chỗ** để đảm bảo tính duy nhất.
- **Giấy phép cấp ra cho key tri ân chính là mã `PX-...`** (không sinh key hex ngẫu nhiên), để Launcher và Cloudflare đối chiếu được cùng một giá trị.

### 3.2 Chuẩn hoá dữ liệu nhập

Mọi mã đều đi qua `db.normalizeCode()` trước khi so khớp: cắt khoảng trắng, chuyển chữ hoa, gộp gạch nối thừa. Người dùng dán ` px-a8k2-9m4p-x7n1 ` cũng khớp với `PX-A8K2-9M4P-X7N1`.

---

## 4. Slash Commands

| Lệnh | Quyền | Mô tả |
| :--- | :--- | :--- |
| `/panel` | Admin | Đăng panel thành viên (3 khối: hướng dẫn · giấy phép · thiết bị & hỗ trợ) |
| `/generatecode [amount]` | Admin | Tạo mã thường `KEY-xxxxxxxx`, gửi vào DM của admin |
| `/genkey <user> [tier]` | Admin | Phát hành key tri ân `PX-...`, đăng ký redeem được, gửi DM cho người nhận |
| `/check-key <user>` | Admin | Xem trạng thái giấy phép, mã đã dùng và log hoạt động |
| `/blacklist <user> [reason]` | Admin | Blacklist vĩnh viễn + thu hồi toàn bộ key (có bước xác nhận) |
| `/unblacklist <user>` | Admin | Gỡ blacklist (key cũ vẫn giữ trạng thái thu hồi) |
| `/reset-hwid [key_code]` | Người dùng | Giải phóng thiết bị (**có dialog xác nhận**) |
| `/revoke-key <key_code> [reason]` | Admin | Khóa key tri ân trên hệ thống |
| `/supporter-init-db` | Admin | Khởi tạo bảng `supporter_keys` trên Cloudflare D1 |

Deploy slash command sau khi sửa:

```bash
cd PTX_Bot && npm run deploy
```

---

## 5. Nút Trên Panel

| Nút | Hành vi |
| :--- | :--- |
| **Kích Hoạt Mã** | Mở modal nhập mã; chấp nhận cả `KEY-` và `PX-` |
| **Giấy Phép Của Tôi** | Liệt kê toàn bộ giấy phép đang hoạt động, gắn nhãn `GIẤY PHÉP` / `KEY TRI ÂN` |
| **Nhận Vai Trò Tri Ân** | Cấp `BUYER_ROLE_ID`; báo rõ nếu đã có vai trò rồi |
| **Giải Phóng Thiết Bị** | Mở **dialog xác nhận** trước khi thực sự reset HWID |

---

## 6. Luồng Vận Hành Thực Tế

### 6.1 Khởi tạo Database D1 (một lần)

1. Admin gõ `/supporter-init-db`.
2. Bot gọi Worker tạo bảng `supporter_keys`.

### 6.2 Khi có người ủng hộ dự án

1. Admin gõ `/genkey user:@TênNgườiDùng`.
2. Bot gọi D1 sinh mã (VD: `PX-K92B-W8M1-X4D2`), gửi tin nhắn riêng cho người đó kèm hướng dẫn kích hoạt.
3. Bot **tự đăng ký** mã này vào `redeem_codes`, ghi log `SUPPORTER_KEY_GENERATED`.

### 6.3 Người hỗ trợ nhận giấy phép và vai trò tri ân

1. Người dùng mở panel, bấm **Kích Hoạt Mã**, dán mã `PX-...`.
2. Bot cấp giấy phép (chính là mã `PX-...`), ghi log `SUPPORTER_KEY_REDEEMED`.
3. Người dùng bấm **Nhận Vai Trò Tri Ân** để nhận `BUYER_ROLE_ID`.

### 6.4 Khi người dùng đổi máy tính

1. Người dùng bấm **Giải Phóng Thiết Bị** trên panel (hoặc gõ `/reset-hwid`).
2. Bot tra cứu D1 qua `/admin/lookup`. Nếu tài khoản chưa có key, key chưa kích hoạt, key bị thu hồi hoặc key không thuộc về người yêu cầu → bot báo rõ lý do và **dừng luôn**, không hiện dialog xác nhận.
3. Nếu đủ điều kiện, bot hiện **dialog xác nhận** — người dùng phải bấm **Xác Nhận Giải Phóng**; bấm **Huỷ** thì không có gì thay đổi.
4. Bot gọi Worker kiểm tra cooldown:
   - Đã qua 4 ngày → xóa HWID cũ, cho phép kích hoạt lại trên máy mới.
   - Chưa đủ 4 ngày → báo số giờ cần chờ còn lại.

Kết quả được cập nhật **ngay trên tin nhắn dialog** (trạng thái "Đang Xử Lý…" → kết quả cuối), không sinh thêm tin nhắn rác.

### 6.5 Khi phát hiện chia sẻ key hoặc vi phạm

1. Admin gõ `/revoke-key key_code:PX-K92B-W8M1-X4D2 reason:"Chia sẻ key trái phép"`.
2. Key bị đánh dấu `is_blocked = 1`. Lần tới khi Launcher của họ mở lên, hệ thống sẽ tự động tước huy hiệu.

---

## 7. Kiểm Thử

Bộ test chạy hoàn toàn cô lập, không ảnh hưởng `whitelist.db` thật và không gọi Worker thật:

```bash
cd PTX_Bot && npm test              # chạy cả hai bộ
cd PTX_Bot && npm run test:db       # chỉ test tầng database
cd PTX_Bot && npm run test:interaction  # chỉ test luồng interaction
```

- **`test-db.js`** — 15 nhóm: migration legacy, tạo/redeem code, chặn mã đã dùng, đa key trên một user, blacklist/unblacklist, chuẩn hoá mã, **key tri ân `PX-` redeem như code thường** và **`registerRedeemCode` idempotent**.
- **`test-interaction.js`** — 9 nhóm cho luồng Reset HWID: dialog xác nhận, pre-check D1, gửi `discord_id` cho người dùng thường, bỏ qua ràng buộc cho admin, hiển thị lỗi 404/429, và **chống hồi quy lỗi `InteractionAlreadyReplied`** (mock mô phỏng đúng guard của discord.js).

---

## 8. Truy Vấn D1 Nhanh

```sql
-- Xóa toàn bộ key
DELETE FROM supporter_keys;

-- Xem toàn bộ key
SELECT * FROM supporter_keys;
```
