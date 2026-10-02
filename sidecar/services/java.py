from __future__ import annotations

import io
import os
import platform
import re
import subprocess
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from sidecar.services.tasks import TaskCancelled, TaskContext, start_task
from sidecar.utils.path_resolver import get_runtimes_dir
from sidecar.utils.file_ops import safe_rmtree, safe_write_text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADOPTIUM_API = "https://api.adoptium.net/v3/assets/latest/{major}/hotspot?os=windows&arch=x64&image_type=jre&heap_size=normal"
DOWNLOAD_CHUNK = 1 << 17  # 128 KiB

# The Adoptium API hands back a github.com download link. GitHub is frequently
# blocked or throttled (the launcher then dies with WinError 10060 on connect),
# so every download goes through a source chain instead of a single URL.
# These mirrors publish byte-identical artifacts (same filename, same size).
ADOPTIUM_MIRRORS: Tuple[str, ...] = (
    "https://mirrors.tuna.tsinghua.edu.cn/Adoptium",
    "https://mirrors.cernet.edu.cn/Adoptium",
)

# Last-resort source on a completely different CDN (Microsoft). It is a full JDK
# (~200 MB instead of ~58 MB) and only exists for the LTS majors, but it beats
# leaving the user with no Java at all.
MICROSOFT_JDK_URL = "https://aka.ms/download-jdk/microsoft-jdk-{major}-windows-x64.zip"
MICROSOFT_JDK_MAJORS: Tuple[int, ...] = (17, 21, 25)

# (connect, read) timeouts: a dead host must fail fast so we can try the next
# source, while a slow-but-working download still gets 60 s per chunk.
DOWNLOAD_CONNECT_TIMEOUT = 15
DOWNLOAD_READ_TIMEOUT = 60

# Well-known install roots to probe on Windows.
_SCAN_ROOTS: List[str] = [
    r"C:\Program Files\Java",
    r"C:\Program Files\Eclipse Adoptium",
    r"C:\Program Files\Microsoft",
    r"C:\Program Files\Zulu",
    r"C:\Program Files\BellSoft\LibericaJDK",
    r"C:\Program Files (x86)\Java",
]

# Registry hives/keys that list installed JREs/JDKs on Windows.
_REGISTRY_KEYS: List[Tuple[str, str]] = [
    ("HKLM", r"SOFTWARE\JavaSoft\Java Runtime Environment"),
    ("HKLM", r"SOFTWARE\JavaSoft\JRE"),
    ("HKLM", r"SOFTWARE\JavaSoft\Java Development Kit"),
    ("HKLM", r"SOFTWARE\JavaSoft\JDK"),
    ("HKLM", r"SOFTWARE\WOW6432Node\JavaSoft\Java Runtime Environment"),
    ("HKLM", r"SOFTWARE\WOW6432Node\JavaSoft\JRE"),
    ("HKLM", r"SOFTWARE\Eclipse Adoptium\JRE"),
    ("HKLM", r"SOFTWARE\Eclipse Foundation\JDK"),
]

_JAVA_VERSION_RE = re.compile(
    r'version\s+"?(?:1\.)?(\d+)[\._]?(\d*)[\._]?(\d*)[_\d]*"?',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Version mapping: Minecraft → required Java major
# ---------------------------------------------------------------------------

# Java majors the launcher can download / manage itself (Eclipse Temurin JREs).
SUPPORTED_JAVA_MAJORS: Tuple[int, ...] = (8, 17, 21, 25)

# First year-based release. From 26.1 on, Mojang ships class file version 69.0,
# i.e. the game only runs on Java 25 (or newer).
YEAR_SCHEME_FIRST_RELEASE = 26

# Matrix exposed to the UI (GET /api/minecraft/java → version_matrix).
JAVA_VERSION_MATRIX: Dict[str, int] = {
    "lt_1.17": 8,
    "1.17_to_1.20.4": 17,
    "1.20.5_to_1.21": 21,
    "gte_26": 25,
}


def required_java_for_mc(mc_version: str) -> int:
    """
    Return the minimum Java major version required for a given MC version string.

    Matrix:
      MC < 1.17           → Java 8
      1.17 ≤ MC < 1.20.5  → Java 17
      1.20.5 ≤ MC < 26    → Java 21
      MC ≥ 26 (26.1, …)   → Java 25

    Since 2026 Mojang uses year-based version numbers: `26.3` is the third game
    drop of 2026 and is compiled for Java 25 (class file version 69.0). Running
    it on Java 21 fails with `UnsupportedClassVersionError`.
    """
    parsed = _parse_mc_version(mc_version)
    if parsed is None:
        return 21  # default for unparseable strings: modern installers need 21+

    release, drop = parsed
    if release >= YEAR_SCHEME_FIRST_RELEASE:
        return 25
    if release < 17:
        return 8
    if (release, drop) < (20, 5):
        return 17
    return 21


def _parse_mc_version(version: str) -> Optional[Tuple[int, int]]:
    """
    Parse a Minecraft version string into a comparable ``(release, drop)`` pair.

    Understands both numbering schemes:

    * legacy  : ``1.20.4``, ``1.21``, ``1.21.11``      → (20, 4), (21, 0), (21, 11)
    * year    : ``26.3``, ``26.1.2``                   → (26, 3), (26, 1)
    * snapshots: ``26.3-snapshot-10``, ``26.3-pre-1``, ``26.3-rc-2`` → (26, 3)
    * week snapshots: ``25w46a``, ``26w14a``           → (25, 0), (26, 0)

    Legacy minors never exceed 21 while the year scheme starts at 26, so the
    returned pair keeps both schemes correctly ordered against each other.
    """
    raw = (version or "").strip().lower()
    if not raw:
        return None

    # Week-based snapshots: "25w46a" / "26w14a"
    m = re.match(r"^(\d{2})w(\d+)[a-z]?$", raw)
    if m:
        return int(m.group(1)), 0

    # Drop tails ("-snapshot-10", "-pre-1", "-rc-2") do not change the Java need.
    raw = re.sub(r"-(?:snapshot|pre|rc)[-.]?\d+$", "", raw)

    m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", raw)
    if not m:
        return None

    first = int(m.group(1))
    if first == 1:  # legacy "1.20.4" / "1.21.11"
        return int(m.group(2)), int(m.group(3) or 0)
    if first >= YEAR_SCHEME_FIRST_RELEASE - 1:  # year-based "26.3"
        return first, int(m.group(2))
    return None


def to_console_java_exe(path_str: str) -> str:
    """Ensure path points to java.exe (console binary) rather than javaw.exe."""
    p = (path_str or "").strip()
    if not p:
        return ""
    if p.lower().endswith("javaw.exe"):
        cand = Path(p).with_name("java.exe")
        if cand.is_file():
            return str(cand)
        return p[:-9] + "java.exe"
    return p


def _candidate_pools(
    installs: List[Dict[str, Any]], target_major: int
) -> List[List[Dict[str, Any]]]:
    """
    Fallback pools for `resolve_java_executable`, best pool first.

    * pool 1 — runtimes new enough for the game, oldest first (closest match);
    * pool 2 — every runtime we could parse, newest first;
    * pool 3 — raw scan order (runtimes whose version we could not read).
    """
    usable = [i for i in installs if i.get("major")]
    if target_major <= 0:
        return [
            sorted(usable, key=lambda i: i["major"], reverse=True),
            installs,
        ]

    sufficient = sorted(
        [i for i in usable if i["major"] >= target_major],
        key=lambda i: i["major"],
    )
    return [
        sufficient,
        sorted(usable, key=lambda i: i["major"], reverse=True),
        installs,
    ]


def resolve_java_executable(mc_version: str = "", custom_path: str = "") -> str:
    """
    Resolve an absolute path to a suitable java.exe binary.

    Resolution order:
      1. User-configured custom_path — unless it is too old for *mc_version*
         (e.g. Java 21 configured while Minecraft 26.3 needs Java 25).
      2. PhantomX-managed runtime (<runtimes_dir>/jre-{target}/bin/java.exe).
      3. First detected installation matching the required major version.
      4. Oldest detected installation that is still new enough, else the newest.
      5. PATH lookup for 'java.exe' / 'java'.
    Always ensures the executable is java.exe (console app, suitable for CLI installers).
    """
    target_major = required_java_for_mc(mc_version) if mc_version else 0
    pinned = ""

    # 1. Custom path
    if custom_path and custom_path.strip():
        cp = to_console_java_exe(custom_path.strip())
        if Path(cp).is_file():
            pinned = cp
            if target_major <= 0:
                return cp
            info = get_java_info(cp)
            major = info.get("major") if info else None
            if major is None or major >= target_major:
                return cp
            # A pinned Java that cannot load the game's class files is worse than
            # no choice at all: `UnsupportedClassVersionError` at startup. Look
            # for a runtime that can actually run this version instead.
            logger.warning(
                f"Configured Java {major} ({cp}) is too old for Minecraft "
                f"{mc_version} — Java {target_major}+ required. Searching for a "
                f"newer runtime."
            )

    # 2. PhantomX-managed runtimes
    if target_major > 0:
        managed_exe = get_runtimes_dir() / f"jre-{target_major}" / "bin" / "java.exe"
        if managed_exe.is_file():
            return str(managed_exe)

    # 3 & 4. Scanned installations
    installs = scan_java_installations()
    if target_major > 0:
        for item in installs:
            if item.get("major") == target_major:
                p = to_console_java_exe(item.get("path", ""))
                if Path(p).is_file():
                    return p

    # No exact match: take the oldest runtime that still satisfies the game
    # (Java is backwards compatible, so Java 25 happily runs a Java 21 build).
    # Old loaders (Forge 1.12.2 …) dislike *much* newer JVMs, hence "oldest that
    # is good enough" instead of "newest available". When nothing is good enough
    # we still hand back the newest one so the error names a real Java.
    for pool in _candidate_pools(installs, target_major):
        for item in pool:
            p = to_console_java_exe(item.get("path", ""))
            if Path(p).is_file():
                return p

    # 5. Check PATH
    from shutil import which
    found = which("java.exe") or which("java")
    if found:
        return str(Path(found).resolve())

    # Nothing newer was available — keep the pinned runtime so behaviour is
    # unchanged from before (the game will report its own Java error).
    return pinned


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_java_version(output: str) -> Optional[int]:
    """
    Extract the Java major version from the text output of `java -version`.
    Returns None if unparseable.
    """
    m = _JAVA_VERSION_RE.search(output)
    if not m:
        return None
    first = int(m.group(1))
    # 1.8.x → 8, 17.x → 17, 21 → 21
    return int(m.group(2)) if first == 1 and m.group(2) else first


def get_java_info(java_exe: str | Path) -> Optional[Dict[str, Any]]:
    """
    Run `java -version` on *java_exe* and return a normalised dict, or None on
    failure.  Output is on stderr for all known JVM implementations.
    """
    exe = str(java_exe)
    try:
        result = subprocess.run(
            [exe, "-version"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        raw = (result.stderr or result.stdout or "").strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    major = _parse_java_version(raw)
    if major is None:
        return None

    arch = "x64" if "64-Bit" in raw else ("x86" if "32-Bit" in raw else "unknown")
    version_line = raw.splitlines()[0] if raw else "unknown"

    return {
        "path": exe,
        "version_string": version_line,
        "major": major,
        "arch": arch,
    }


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def _probe_exe(candidate: Path) -> Optional[Dict[str, Any]]:
    """Return a JavaInstall dict if *candidate* is a working java.exe, else None."""
    if not candidate.is_file():
        return None
    info = get_java_info(candidate)
    return info


def _find_java_in_dir(base: Path) -> List[Dict[str, Any]]:
    """Scan a directory root for java executables (one or two levels deep)."""
    results: List[Dict[str, Any]] = []
    if not base.is_dir():
        return results

    # Pattern: base/bin/java.exe  or  base/jre-XX/bin/java.exe
    for pattern in ("bin/java.exe", "bin/javaw.exe"):
        hit = _probe_exe(base / pattern)
        if hit:
            results.append(hit)
            break

    for child in base.iterdir():
        if not child.is_dir():
            continue
        for pattern in ("bin/java.exe",):
            hit = _probe_exe(child / pattern)
            if hit:
                results.append(hit)
                break

    return results


def _scan_registry() -> List[str]:
    """
    Query the Windows Registry for JavaHome paths.
    Returns a list of paths (may not exist on disk yet).
    Silently skips on non-Windows or if winreg is unavailable.
    """
    paths: List[str] = []
    if platform.system() != "Windows":
        return paths

    try:
        import winreg
    except ImportError:
        return paths

    def _hive(name: str):
        return getattr(winreg, name, None)

    hklm = _hive("HKEY_LOCAL_MACHINE")
    if hklm is None:
        return paths

    for _hive_name, key_path in _REGISTRY_KEYS:
        try:
            with winreg.OpenKey(hklm, key_path) as hkey:  # type: ignore[attr-defined]
                # Sub-keys are version strings like "21.0.3"
                i = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(hkey, i)  # type: ignore[attr-defined]
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(hkey, sub_name) as subkey:  # type: ignore[attr-defined]
                            home, _ = winreg.QueryValueEx(subkey, "JavaHome")  # type: ignore[attr-defined]
                            if home and isinstance(home, str):
                                paths.append(home)
                    except OSError:
                        continue
        except OSError:
            continue

    return paths


def scan_java_installations() -> List[Dict[str, Any]]:
    """
    Discover all JRE/JDK installations visible to the launcher.

    Search order (first unique path wins):
    1. JAVA_HOME environment variable
    2. PATH (first `java.exe` on PATH)
    3. Windows Registry (JavaHome values)
    4. Well-known install directories
    5. PhantomX-managed runtimes in <runtimes_dir>
    """
    seen_paths: set[str] = set()
    results: List[Dict[str, Any]] = []

    def _add(info: Dict[str, Any], source: str) -> None:
        key = info["path"].lower()
        if key not in seen_paths:
            seen_paths.add(key)
            results.append({**info, "source": source})

    # 1. JAVA_HOME
    java_home = os.environ.get("JAVA_HOME", "").strip()
    if java_home:
        for info in _find_java_in_dir(Path(java_home)):
            _add(info, "env_java_home")

    # 2. PATH — `java -version` directly, which may resolve via PATH
    from shutil import which
    java_on_path = which("java")
    if java_on_path:
        info = get_java_info(java_on_path)
        if info:
            _add(info, "system_path")

    # 3. Windows Registry
    for reg_path in _scan_registry():
        for info in _find_java_in_dir(Path(reg_path)):
            _add(info, "registry")

    # 4. Well-known roots
    for root_str in _SCAN_ROOTS:
        for info in _find_java_in_dir(Path(root_str)):
            _add(info, "system")

    # 5. PhantomX-managed runtimes
    runtimes_dir = get_runtimes_dir()
    if runtimes_dir.is_dir():
        for child in sorted(runtimes_dir.iterdir()):
            if not child.is_dir():
                continue
            for info in _find_java_in_dir(child):
                _add(info, "phantomx")

    logger.info(f"Java scan found {len(results)} installation(s)")
    return results


# ---------------------------------------------------------------------------
# Adoptium download
# ---------------------------------------------------------------------------

def _fetch_adoptium_asset(major: int) -> Optional[Dict[str, Any]]:
    """
    Call the Adoptium API to get the download URL + size for a JRE build.
    Returns a dict with keys: download_url, filename, size_bytes.
    Returns None on network error or unexpected response structure.
    """
    url = ADOPTIUM_API.format(major=major)
    logger.info(f"Querying Adoptium API: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PhantomX-Launcher/2.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            import json as _json
            data = _json.loads(resp.read())
    except urllib.error.URLError as e:
        logger.error(f"Adoptium API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Adoptium API unexpected error: {e}")
        return None

    if not data or not isinstance(data, list) or len(data) == 0:
        logger.error(f"Adoptium API returned empty list for Java {major}")
        return None

    asset = data[0]
    try:
        binary = asset["binary"]
        package = binary["package"]
        return {
            "download_url": package["link"],
            "filename": package["name"],
            "size_bytes": package.get("size", 0),
            "checksum": package.get("checksum", ""),
            "checksum_link": package.get("checksum_link", ""),
        }
    except (KeyError, TypeError) as e:
        logger.error(f"Adoptium API response parse error: {e}")
        return None


def _mirror_asset_urls(major: int, filename: str) -> List[str]:
    """Mirror URLs for an Adoptium filename (`<mirror>/<major>/jre/x64/windows/<zip>`)."""
    if not filename:
        return []
    return [
        f"{base}/{major}/jre/x64/windows/{filename}" for base in ADOPTIUM_MIRRORS
    ]


def _fetch_mirror_asset(major: int) -> Optional[Dict[str, Any]]:
    """
    Discover the newest JRE zip straight from a mirror index.

    Used when api.adoptium.net itself is unreachable: the mirrors expose a plain
    directory listing, so we can pick the newest `OpenJDK{major}U-jre_...zip`
    without the API.
    """
    for base in ADOPTIUM_MIRRORS:
        index_url = f"{base}/{major}/jre/x64/windows/"
        try:
            req = urllib.request.Request(
                index_url, headers={"User-Agent": "PhantomX-Launcher/2.0"}
            )
            with urllib.request.urlopen(req, timeout=DOWNLOAD_CONNECT_TIMEOUT) as resp:
                html = resp.read().decode("utf-8", "replace")
        except Exception as e:
            logger.debug(f"Adoptium mirror index unavailable: {index_url} ({e})")
            continue

        names = sorted(
            set(
                re.findall(
                    rf"OpenJDK{major}U-jre_x64_windows_hotspot_[0-9A-Za-z._+\-]+\.zip",
                    html,
                )
            )
        )
        if not names:
            continue

        filename = names[-1]
        logger.info(f"Adoptium mirror index resolved Java {major}: {filename}")
        return {
            "download_url": f"{base}/{major}/jre/x64/windows/{filename}",
            "filename": filename,
            "size_bytes": 0,
            "checksum": "",
            "checksum_link": "",
        }
    return None


def _download_sources(major: int, asset: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    Ordered (label, url) candidates for the JRE zip.

    1. the official link returned by the Adoptium API (github.com);
    2. the same file on each Adoptium mirror;
    3. Microsoft Build of OpenJDK as a last resort.
    """
    sources: List[Tuple[str, str]] = []
    official = asset.get("download_url") or ""
    if official:
        sources.append((_source_label(official), official))

    for url in _mirror_asset_urls(major, asset.get("filename", "")):
        if url and url != official:
            sources.append((_source_label(url), url))

    if major in MICROSOFT_JDK_MAJORS:
        sources.append(
            ("Microsoft OpenJDK (JDK, dự phòng)", MICROSOFT_JDK_URL.format(major=major))
        )
    return sources


def _source_label(url: str) -> str:
    """Human-readable label for a download URL, derived from its host."""
    host = url.split("/")[2] if url.count("/") >= 2 else url
    if "github.com" in host:
        return "Adoptium (GitHub)"
    if "aka.ms" in host or "visualstudio" in host:
        return "Microsoft OpenJDK"
    return f"Mirror ({host})"


def _download_to_file(
    url: str,
    target: Path,
    ctx: TaskContext,
    total_hint: int = 0,
) -> int:
    """
    Stream *url* into *target*, reporting progress. Returns the byte count.

    Streamed to disk (instead of buffered in RAM) because the Microsoft
    fallback is a ~200 MB JDK. Raises on any network/HTTP failure so the caller
    can fall through to the next source.
    """
    import requests

    target.parent.mkdir(parents=True, exist_ok=True)
    downloaded = 0

    with requests.get(
        url,
        headers={"User-Agent": "PhantomX-Launcher/2.0"},
        stream=True,
        timeout=(DOWNLOAD_CONNECT_TIMEOUT, DOWNLOAD_READ_TIMEOUT),
    ) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length") or total_hint or 0)

        with open(target, "wb") as fh:
            for chunk in resp.iter_content(DOWNLOAD_CHUNK):
                ctx.check_cancelled()
                if not chunk:
                    continue
                fh.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = int(5 + 85 * downloaded / total)
                    ctx.progress(
                        pct,
                        100,
                        f"Downloading… {downloaded // (1024*1024)} MB / {total // (1024*1024)} MB",
                    )
                else:
                    ctx.progress(50, 100, f"Downloading… {downloaded // (1024*1024)} MB")

    if downloaded == 0:
        raise RuntimeError("Máy chủ trả về 0 byte")
    return downloaded


def _strip_root_extract(zip_data, dest: Path) -> None:
    """
    Extract a ZIP archive into *dest*, stripping the top-level folder.

    *zip_data* may be the archive bytes or a path to a .zip on disk (the
    download is streamed to disk, so we no longer hold it in memory).

    Adoptium archives look like:
      jdk-21.0.3+9-jre/bin/java.exe
      jdk-21.0.3+9-jre/release
      ...

    We strip that root component so the result is:
      <dest>/bin/java.exe
      <dest>/release
      ...

    This ensures the path `bin/java.exe` inside the destination is always
    consistent regardless of Adoptium's versioned folder name (RULE 2).
    """
    source = io.BytesIO(zip_data) if isinstance(zip_data, (bytes, bytearray)) else zip_data
    with zipfile.ZipFile(source) as zf:
        members = zf.infolist()
        if not members:
            return

        # Determine the common root prefix (first path component).
        first_parts = members[0].filename.split("/", 1)
        root_prefix = first_parts[0] + "/" if len(first_parts) > 1 else ""

        dest.mkdir(parents=True, exist_ok=True)
        for member in members:
            # Strip the root folder from the path.
            rel_path = member.filename
            if root_prefix and rel_path.startswith(root_prefix):
                rel_path = rel_path[len(root_prefix):]

            if not rel_path:  # was the root folder entry itself
                continue

            target = dest / rel_path

            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                data = zf.read(member.filename)
                target.write_bytes(data)


def download_java(major: int) -> str:
    """
    Start a background task that downloads and installs JRE *major* from
    Adoptium.  Returns the task_id immediately (RULE 1).
    """
    def _worker(ctx: TaskContext) -> Dict[str, Any]:
        ctx.log(f"Starting Java {major} download via Adoptium API…")
        ctx.progress(0, 100, f"Fetching Adoptium metadata for Java {major}…")

        # ── 1. Resolve metadata (API, then mirror index) ───────────────────
        ctx.check_cancelled()
        asset = _fetch_adoptium_asset(major)
        if asset is None:
            ctx.log(
                "⚠️ Adoptium API unreachable — resolving the build from a mirror index…",
                level="warning",
            )
            asset = _fetch_mirror_asset(major)
        if asset is None:
            raise RuntimeError(
                f"Không lấy được thông tin Java {major} từ Adoptium API lẫn mirror. "
                "Kiểm tra kết nối mạng (hoặc proxy) rồi thử lại."
            )

        total_bytes: int = asset["size_bytes"] or 0
        filename: str = asset["filename"]
        ctx.log(f"Resolved: {filename}" + (f" ({total_bytes // (1024*1024)} MB)" if total_bytes else ""))

        # ── 2. Download with a source chain ────────────────────────────────
        # The official link lives on github.com, which many networks block. Each
        # source gets a short connect timeout so we move on quickly instead of
        # hanging for the OS TCP timeout.
        ctx.check_cancelled()
        ctx.progress(5, 100, f"Downloading {filename}…")

        sources = _download_sources(major, asset)
        dest_dir = get_runtimes_dir() / f"jre-{major}"
        archive_path = get_runtimes_dir() / f"jre-{major}.download.zip"
        last_error: Optional[str] = None
        downloaded = 0

        for idx, (label, url) in enumerate(sources, start=1):
            try:
                archive_path.unlink(missing_ok=True)
            except OSError:
                pass

            ctx.log(f"⬇️ Nguồn {idx}/{len(sources)}: {label}")
            try:
                downloaded = _download_to_file(url, archive_path, ctx, total_bytes)
                ctx.log(f"✅ Tải xong từ {label} ({downloaded // (1024*1024)} MB)")
                break
            except Exception as e:
                last_error = f"{label}: {e}"
                logger.warning(f"Java {major} download source failed — {last_error}")
                ctx.log(f"⚠️ {label} thất bại ({e}) — thử nguồn khác…", level="warning")
        else:
            try:
                archive_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError(
                f"Không thể tải Java {major} từ bất kỳ nguồn nào (GitHub / Adoptium "
                f"mirror / Microsoft). Lỗi cuối: {last_error}. "
                "Hãy kiểm tra mạng hoặc cài Java thủ công rồi trỏ java_path tới java.exe."
            )

        ctx.progress(90, 100, "Extracting archive…")

        # ── 3. Wipe old installation & extract ─────────────────────────────
        ctx.check_cancelled()

        if dest_dir.exists():
            ctx.log(f"Removing existing installation at {dest_dir}…")
            result = safe_rmtree(dest_dir)
            if not result.ok:
                raise RuntimeError(f"Could not remove old JRE: {result.error}")

        try:
            _strip_root_extract(archive_path, dest_dir)
        except (zipfile.BadZipFile, Exception) as e:
            raise RuntimeError(f"Extraction failed: {e}") from e
        finally:
            try:
                archive_path.unlink(missing_ok=True)
            except OSError:
                pass

        # ── 4. Verify ──────────────────────────────────────────────────────
        java_exe = dest_dir / "bin" / "java.exe"
        if not java_exe.is_file():
            raise RuntimeError(
                f"Extraction succeeded but bin/java.exe not found at {dest_dir}. "
                "The archive may have an unexpected layout."
            )

        info = get_java_info(java_exe)
        if info is None:
            raise RuntimeError("Extracted java.exe did not respond to -version. The archive may be corrupted.")

        # Auto-save newly installed Java to settings so the launcher recognizes it immediately
        from sidecar.services.core_service import save_settings
        saved_settings = save_settings({"java_path": str(java_exe)})
        ctx.log(f"Auto-saved java_path in settings: {java_exe}")

        ctx.log(f"Java {major} installed successfully at {dest_dir}")
        ctx.log(f"Version: {info['version_string']}")
        ctx.progress(100, 100, f"Java {major} ready")

        return {
            "major": major,
            "path": str(java_exe),
            "version_string": info["version_string"],
            "dest": str(dest_dir),
            "settings": saved_settings,
        }

    task_id = start_task(_worker, name=f"java-download-{major}")
    logger.info(f"Java {major} download task started: {task_id}")
    return task_id
