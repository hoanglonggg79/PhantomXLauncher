"""Đồng bộ phiên bản PhantomX Launcher trên toàn bộ file khai báo version.

Cách dùng:
    python bump-version.py 1.2.2

Các mục "khóa cứng" (pattern biết trước, sửa chính xác 1 vị trí):
    app/package.json                     (frontend)
    app/package-lock.json                (chỉ version gốc, không đụng dependency)
    app/src-tauri/Cargo.toml             (Rust shell)
    app/src-tauri/tauri.conf.json        (Rust shell)
    scr/core.py                          (APP_VERSION - nguồn sự thật của app)
    version.txt                          (update checker đọc từ GitHub raw)
    sidecar/services/marketplace.py      (User-Agent)
    sidecar/services/modpack.py          (User-Agent)
    sidecar/services/diagnostics.py      (fallback)
    sidecar/services/changelog.py        (fallback)

Sau đó là bước QUÉT TỔNG (sweep): mọi file .py/.ts/.tsx/.js được git track còn
chứa version cũ (khớp nguyên specific, ví dụ "1.2.1" nhưng không đụng
"1.2.18") đều được đổi thành version mới. Nhờ vậy các tham chiếu rời rạc —
fallback getattr trong discord_rpc.py, placeholder trong ConnectionGate.tsx,
hay chỗ tham chiếu mới thêm sau này — không bao giờ bị bỏ sót, kể cả khi quên
khai báo vào danh sách trên.

Cuối cùng script verify lại: nếu vẫn còn file nào trong phạm vi quét chứa
version cũ, nó sẽ bị liệt kê ra để sửa tay.

Script này cũng được GitHub Actions (release.yml) gọi tự động với tham số là
tên tag. Nhờ vậy APP_VERSION của bản build luôn khớp version.txt, tránh tình
trạng app báo "có bản cập nhật" mãi không dứt.
"""

import sys
import re
import subprocess
from pathlib import Path

if sys.platform == "win32":
    try:
        if sys.stdout.encoding != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent

# Phạm vi quét tổng: chỉ file source code, không quét .md (ghi chú lịch sử
# phiên bản trong README/release notes phải giữ nguyên) và không quét lockfile
# (chứa version dependency trùng số với version app là chuyện bình thường).
SWEEP_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".txt"}
SWEEP_EXCLUDE_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock",
    # Docstring của script dùng version cũ làm ví dụ minh họa, không phải tham chiếu app.
    "bump-version.py",
}

def get_current_version() -> str:
    core_py = ROOT_DIR / "scr" / "core.py"
    if core_py.exists():
        match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', core_py.read_text(encoding="utf-8"))
        if match:
            return match.group(1)
    return "Unknown"

def parse_semver(ver: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", ver.strip())
    if not match:
        raise ValueError(f"Phiên bản '{ver}' không đúng định dạng semver (ví dụ: 1.2.2)")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))

def update_file(path: Path, pattern: str, replacement: str, description: str) -> bool:
    if not path.exists():
        print(f"  ⚠️  Bỏ qua (không tìm thấy file): {path.relative_to(ROOT_DIR)}")
        return False

    content = path.read_text(encoding="utf-8")
    new_content, count = re.subn(pattern, replacement, content)
    if count == 0:
        print(f"  ⚠️  Không tìm thấy pattern cần thay đổi trong: {path.relative_to(ROOT_DIR)}")
        return False

    path.write_text(new_content, encoding="utf-8")
    print(f"  ✅ Đã cập nhật ({count} chỗ): {path.relative_to(ROOT_DIR)} [{description}]")
    return True

def update_package_lock(path: Path, new_ver: str) -> bool:
    """Sửa version gốc của lockfile, KHÔNG đụng version của từng dependency.

    package-lock.json chứa hàng nghìn dòng `"version"` của package con, nên chỉ
    áp regex lên đúng 2 vị trí: đầu file (trước key "packages") và entry
    packages[""] — vốn luôn phản chiếu version của package.json.
    """
    if not path.exists():
        print(f"  ⚠️  Bỏ qua (không tìm thấy file): {path.relative_to(ROOT_DIR)}")
        return False

    content = path.read_text(encoding="utf-8")
    head, sep, tail = content.partition('"packages"')
    if not sep:
        print(f'  ⚠️  Không tìm thấy key "packages" trong: {path.relative_to(ROOT_DIR)}')
        return False

    count = 0

    # (a) version của package gốc ở đầu file
    head, n = re.subn(r'("version"\s*:\s*)"[^"]+"', rf'\g<1>"{new_ver}"', head)
    count += n

    # (b) version trong packages[""]
    tail, n = re.subn(
        r'^(\s*"":\s*\{\s*\n\s*"name"\s*:\s*"[^"]*",\s*\n\s*"version"\s*:\s*)"[^"]+"',
        rf'\g<1>"{new_ver}"',
        tail,
        count=1,
        flags=re.MULTILINE,
    )
    count += n

    if count == 0:
        print(f"  ⚠️  Không tìm thấy version gốc trong: {path.relative_to(ROOT_DIR)}")
        return False

    path.write_text(head + sep + tail, encoding="utf-8")
    print(f"  ✅ Đã cập nhật ({count} chỗ): {path.relative_to(ROOT_DIR)} [lockfile version]")
    return True

def update_version_txt(path: Path, new_ver: str) -> bool:
    """version.txt là thứ update checker đem ra so với APP_VERSION của app."""
    if not path.exists():
        print(f"  ⚠️  Bỏ qua (không tìm thấy file): {path.relative_to(ROOT_DIR)}")
        return False

    path.write_text(f"{new_ver}\n", encoding="utf-8")
    print(f"  ✅ Đã cập nhật: {path.relative_to(ROOT_DIR)} [update checker]")
    return True

def tracked_source_files() -> list[Path]:
    """File source được git track (tự tôn trọng .gitignore, bỏ node_modules/Bot…).

    Qua `git ls-files` thay vì os.walk để không đụng file build output hay thư
    mục lạ. Fallback sang os.walk (prune các thư mục ồn ào) khi git không có.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True, check=True, cwd=ROOT_DIR,
        ).stdout
        return [ROOT_DIR / line for line in out.splitlines() if line.strip()]
    except Exception:
        pass

    prune = {".git", "node_modules", "Bot", "__pycache__", ".venv", "venv",
             "dist", "dist-ssr", "target", "build", "staging", "PhantomXData",
             ".zcode", ".workbuddy-ai", ".wrangler", "logs"}
    files: list[Path] = []
    for path in ROOT_DIR.rglob("*"):
        if any(part in prune for part in path.relative_to(ROOT_DIR).parts):
            continue
        if path.is_file():
            files.append(path)
    return files

def sweep_old_version(old_ver: str, new_ver: str) -> int:
    """Đổi mọi tham chiếu nguyên vẹn của version cũ còn sót trong source.

    Khớp có biên số: "1.2.1" được đổi, nhưng "^1.2.18" hay "21.1.2" thì không
    ((?<![\\d.]) … (?![\\d.])). Trả về số file đã sửa.
    """
    boundary = re.compile(rf"(?<![\d.]){re.escape(old_ver)}(?![\d.])")
    changed = 0
    for path in tracked_source_files():
        if path.suffix.lower() not in SWEEP_EXTENSIONS:
            continue
        if path.name in SWEEP_EXCLUDE_FILES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new_content, count = boundary.subn(new_ver, content)
        if count:
            path.write_text(new_content, encoding="utf-8")
            changed += 1
            print(f"  ✅ Quét tổng ({count} chỗ): {path.relative_to(ROOT_DIR)}")
    return changed

def verify_no_leftovers(old_ver: str, new_ver: str) -> list[Path]:
    """Liệt kê file trong phạm vi quét vẫn còn version cũ (phải là rỗng)."""
    boundary = re.compile(rf"(?<![\d.]){re.escape(old_ver)}(?![\d.])")
    leftovers: list[Path] = []
    for path in tracked_source_files():
        if path.suffix.lower() not in SWEEP_EXTENSIONS:
            continue
        if path.name in SWEEP_EXCLUDE_FILES:
            continue
        try:
            if boundary.search(path.read_text(encoding="utf-8")):
                leftovers.append(path)
        except (UnicodeDecodeError, OSError):
            continue
    return leftovers

def bump(new_ver: str):
    new_ver = new_ver.strip().lstrip("v")
    try:
        parse_semver(new_ver)
    except ValueError as e:
        print(f"❌ Lỗi: {e}")
        sys.exit(1)

    old_ver = get_current_version()
    print(f"\n🚀 Đang nâng cấp phiên bản PhantomX Launcher:")
    print(f"   {old_ver} ➔ {new_ver}\n")

    changes = []

    # 1. Frontend: app/package.json
    changes.append(update_file(
        ROOT_DIR / "app" / "package.json",
        r'("name":\s*"app",\s*\n\s*"private":\s*true,\s*\n\s*"version":\s*)"[^"]+"',
        rf'\g<1>"{new_ver}"',
        "package.json"
    ))

    # 2. Frontend lockfile: app/package-lock.json
    changes.append(update_package_lock(ROOT_DIR / "app" / "package-lock.json", new_ver))

    # 3. Rust Shell: app/src-tauri/Cargo.toml
    changes.append(update_file(
        ROOT_DIR / "app" / "src-tauri" / "Cargo.toml",
        r'(\[package\][\s\S]*?version\s*=\s*)"[^"]+"',
        rf'\g<1>"{new_ver}"',
        "Cargo.toml"
    ))

    # 4. Rust Shell: app/src-tauri/tauri.conf.json
    changes.append(update_file(
        ROOT_DIR / "app" / "src-tauri" / "tauri.conf.json",
        r'("version"\s*:\s*)"[^"]+"',
        rf'\g<1>"{new_ver}"',
        "tauri.conf.json"
    ))

    # 5. Core Python: scr/core.py
    changes.append(update_file(
        ROOT_DIR / "scr" / "core.py",
        r'(APP_VERSION\s*=\s*)"[^"]+"',
        rf'\g<1>"{new_ver}"',
        "APP_VERSION"
    ))

    # 6. Update checker: version.txt
    changes.append(update_version_txt(ROOT_DIR / "version.txt", new_ver))

    # 7. Sidecar Marketplace: sidecar/services/marketplace.py
    changes.append(update_file(
        ROOT_DIR / "sidecar" / "services" / "marketplace.py",
        r'(USER_AGENT\s*=\s*"PhantomXLauncher/)[^ ]+',
        rf'\g<1>{new_ver}',
        "USER_AGENT"
    ))

    # 8. Sidecar Modpack: sidecar/services/modpack.py (bản sao USER_AGENT)
    changes.append(update_file(
        ROOT_DIR / "sidecar" / "services" / "modpack.py",
        r'(USER_AGENT\s*=\s*"PhantomXLauncher/)[^ ]+',
        rf'\g<1>{new_ver}',
        "USER_AGENT"
    ))

    # 9. Sidecar Diagnostics: sidecar/services/diagnostics.py
    changes.append(update_file(
        ROOT_DIR / "sidecar" / "services" / "diagnostics.py",
        r'(getattr\(core,\s*"APP_VERSION",\s*)"[^"]+"',
        rf'\g<1>"{new_ver}"',
        "app_version fallback"
    ))

    # 10. Sidecar Changelog: sidecar/services/changelog.py
    changes.append(update_file(
        ROOT_DIR / "sidecar" / "services" / "changelog.py",
        r'(getattr\(core,\s*"APP_VERSION",\s*)"[^"]+"',
        rf'\g<1>"{new_ver}"',
        "current_version fallback"
    ))

    # 11. Quét tổng: mọi tham chiếu version cũ còn sót trong file source
    # (fallback getattr trong discord_rpc.py, placeholder trong ConnectionGate.tsx,
    # và bất kỳ chỗ tham chiếu mới nào thêm sau). Bỏ qua khi version cũ không
    # xác định được hoặc trùng version mới (chạy lại trên cùng version).
    sweep_count = 0
    try:
        needs_sweep = old_ver != "Unknown" and parse_semver(old_ver) != parse_semver(new_ver)
    except ValueError:
        needs_sweep = False
    if needs_sweep:
        print(f"\n🔍 Quét tổng các tham chiếu còn sót của {old_ver}…")
        sweep_count = sweep_old_version(old_ver, new_ver)
        if sweep_count == 0:
            print("  ✅ Không còn sót chỗ nào.")
    changes.append(sweep_count > 0)

    # 12. Verify: bắt buộc phải sạch, nếu không liệt kê ra để sửa tay
    leftovers = verify_no_leftovers(old_ver, new_ver) if old_ver not in ("Unknown", new_ver) else []
    if leftovers:
        print(f"\n⚠️  Vẫn còn {len(leftovers)} file chứa {old_ver} sau khi quét:")
        for path in leftovers:
            print(f"     - {path.relative_to(ROOT_DIR)}")
        print("  Hãy sửa tay các file trên hoặc thêm pattern khóa cứng cho chúng.")
    else:
        print(f"\n✅ Verify: sạch — không còn tham chiếu {old_ver} nào trong phạm vi quét.")

    successful = sum(1 for c in changes if c)
    print(f"\n🎉 Hoàn thành! Đã cập nhật thành công {successful}/{len(changes)} mục sang phiên bản {new_ver}.\n")

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        curr = get_current_version()
        print(__doc__)
        print(f"Phiên bản hiện tại: {curr}")
        sys.exit(0)

    bump(sys.argv[1])

if __name__ == "__main__":
    main()
