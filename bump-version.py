"""Đồng bộ phiên bản PhantomX Launcher trên toàn bộ file khai báo version.

Cách dùng:
    python bump-version.py 1.2.1

Ghi phiên bản mới vào:
    app/package.json                     (frontend)
    app/package-lock.json                (chỉ version gốc, không đụng dependency)
    app/src-tauri/Cargo.toml             (Rust shell)
    app/src-tauri/tauri.conf.json        (Rust shell)
    scr/core.py                          (APP_VERSION - nguồn sự thật của app)
    version.txt                          (update checker đọc từ GitHub raw)
    sidecar/services/marketplace.py      (User-Agent)
    sidecar/services/diagnostics.py      (fallback)
    sidecar/services/changelog.py        (fallback)

Script này cũng được GitHub Actions (release.yml) gọi tự động với tham số là
tên tag. Nhờ vậy APP_VERSION của bản build luôn khớp version.txt, tránh tình
trạng app báo "có bản cập nhật" mãi không dứt.
"""

import sys
import re
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
        raise ValueError(f"Phiên bản '{ver}' không đúng định dạng semver (ví dụ: 1.2.1)")
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

    # 8. Sidecar Diagnostics: sidecar/services/diagnostics.py
    changes.append(update_file(
        ROOT_DIR / "sidecar" / "services" / "diagnostics.py",
        r'(getattr\(core,\s*"APP_VERSION",\s*)"[^"]+"',
        rf'\g<1>"{new_ver}"',
        "app_version fallback"
    ))

    # 9. Sidecar Changelog: sidecar/services/changelog.py
    changes.append(update_file(
        ROOT_DIR / "sidecar" / "services" / "changelog.py",
        r'(getattr\(core,\s*"APP_VERSION",\s*)"[^"]+"',
        rf'\g<1>"{new_ver}"',
        "current_version fallback"
    ))

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
