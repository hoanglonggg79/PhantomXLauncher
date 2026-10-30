# PhantomX Minecraft Launcher (v1.2.2)

<div align="center">

![PhantomX Logo](./icon.png)

### **The Next Gen Minecraft Launcher**
*Engineered for extreme performance, Cyberpunk aesthetics, effortless modding, and seamless gameplay.*

[![Version](https://img.shields.io/badge/version-1.2.1-emerald.svg?style=for-the-badge)](https://github.com/hoanglonggg79/PhantomXLauncher/releases)
[![Tauri](https://img.shields.io/badge/Tauri-2.0-24C8D8?style=for-the-badge&logo=tauri&logoColor=white)](https://tauri.app/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/Python-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg?style=for-the-badge)](./LICENSE)
[![Discord](https://img.shields.io/badge/Discord-Join%20Community-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/PECavu2q4w)

</div>

---

> [!NOTE]
> **Account Support:** PhantomX fully supports **Offline (Cracked)** play and custom skin authentication via **Ely.by** (with automatic `authlib-injector` injection). LAN play and community servers are 100% supported.

---

## What is new in Version 1.2.2

A maintenance release driven by bug reports from players. It stops the marketplace from installing mods that cannot run, makes task cancellation honest, and removes the slow spots when browsing CurseForge.

**Marketplace compatibility**

- The marketplace now derives its version and loader filters from the selected instance instead of letting the UI pick the first hit, so a NeoForge 26.3 jar can no longer be installed into a Fabric 1.20.4 instance.
- Every install is validated twice (API layer and install task): a mismatched loader or Minecraft version is refused with a clear message naming both sides, instead of silently writing a dead jar into `mods/`.
- Vanilla instances cannot load mods at all — the version list shows an explicit notice instead of unrelated files.
- The version filter reads the live version manifest instead of a hardcoded list that stopped at 1.21.4, so 26.x is selectable. Compatibility compares major.minor only, so a 1.21.7 mod still installs on 1.21.8.

**Faster marketplace**

- All Modrinth and CurseForge calls go through one keep-alive session with connection pooling and automatic retries on 429/5xx; previously every request paid a fresh TLS handshake (~1s per call).
- Project metadata is cached for 5 minutes, and the project details and version list are fetched in parallel instead of one after the other.

**Honest cancellation**

- Background tasks record which stage they are in, so cancelling reports "Đã huỷ (dừng ở bước …)" instead of a vague message — including the case where the work finished after the cancel was requested (reported as cancelled, partial result kept, never as success).

**Verifiable Fabric installs**

- The launcher resolves a concrete Fabric loader build before installing, pins it into `instance.json`, and verifies the profile folder actually landed on disk. Launches prefer the pinned profile instead of guessing by sort order, so two Fabric profiles for the same Minecraft version can no longer race.

**Download reliability**

- Mojang downloads use per-thread keep-alive sessions with a pool sized for the download workers, eliminating the "Connection pool is full" warnings and the per-file TLS handshakes.

**Diagnostics**

- GPU detection gets an 8-second budget instead of 3, caches its result for the process lifetime, and falls back to reading `DriverDesc` straight from the registry — `wmic` no longer ships with Windows 11 24H2.

---

## Features

### Isolated Instance Management
- **Total Independence:** Each Minecraft profile lives in its own dedicated directory. Modpacks, configs, resource packs, and worlds never conflict.
- **Dynamic Loader Support:** One-click automated setup for **Vanilla**, **Fabric**, **Forge**, **Quilt**, and **NeoForge**.
- **Instance Actions:** Clone / Duplicate, rename, edit notes, explore local folder via Windows Explorer, and atomic deletion.
- **Preconfigured JVM Optimization:** Integrated with community-proven Aikar JVM flags for ultra-smooth garbage collection and maximum FPS.

### Unified Mod Marketplace
- **Direct Search & Download:** Browse and install thousands of mods directly inside the launcher from **Modrinth v2** and **CurseForge** (via secure Cloudflare Worker proxy).
- **Interactive Lightbox:** Preview screenshot galleries and read formatted project descriptions without leaving the app.
- **Smart Compatibility:** Automatic filtering by game version, loader, and release channel (Release / Beta / Alpha).
- **Instance Running Guard:** Protects against overwriting or modifying files while the instance is actively running.

### 1-Click Modpack Installer
- **Universal Drag & Drop:** Drop `.mrpack` (Modrinth) or `.zip` (CurseForge) directly into the UI.
- **Intelligent Extraction:** Automated manifest parsing, staging directory verification, parallel asset downloads, and atomic instance registration.

### Advanced Diagnostics & System Repair
- **SHA-1 Integrity Verification:** High-speed multi-threaded (`ThreadPoolExecutor`) hash checker comparing version manifests, client JARs, libraries, and asset indexes. Re-downloads only corrupted files without wiping user data.
- **Regex 80/20 Crash Log Analyzer:** Instantly diagnoses the root cause of crashes:
  - **Out of Memory (OOM)** $\rightarrow$ Quick action to increase RAM allocation.
  - **Mod Dependency Conflicts** $\rightarrow$ Identifies missing or incompatible mods with quick navigation to Mod Manager.
  - **Java Version Mismatches** $\rightarrow$ Direct link to switch between Java 8, 17, 21, and 25 (reads the class-file version straight from the crash log).
- **Quick Actions:** One-click **"Copy Log"** button, `options.txt` reset, and global cache cleanup.

### Identity & Skin System
- **Offline Mode:** Simple username-based gameplay with instant UUID generation.
- **Ely.by Integration:** Full OAuth2 login with automatic `authlib-injector` JVM agent injection. Display high-res skins, capes, and player avatars in real time.
- **Hardened Security:** Credentials stored securely via Windows Credential Manager / OS Keyring with Portable Fernet fallback encryption.

### Java Runtime Manager
- **System Discovery:** Auto-scans `PATH`, `JAVA_HOME`, Windows Registry, and well-known installation paths.
- **1-Click Adoptium JRE Downloader:** Automatically download and extract official OpenJDK JRE 8 (Legacy), JRE 17 (Gamma), JRE 21 (Delta) or JRE 25 (Epsilon, needed by Minecraft 26.x).
- **Version-aware auto-selection:** The launcher maps each Minecraft version to the Java it needs (`MC < 1.17` → 8, `1.17–1.20.4` → 17, `1.20.5–1.21.x` → 21, `MC ≥ 26.1` → 25) and silently swaps in a newer runtime instead of failing with `UnsupportedClassVersionError`.

### Ambient Music & Discord Rich Presence
- **Background Music Player:** Built-in relaxing soundtrack with audio wave animations, volume slider, mute toggle, and seamless Webview autoplay unlocking.
- **Dynamic Discord RPC:** Shows rich live presence on your Discord profile:
  - *Browsing Launcher (Idle)*
  - *Dạo quanh Marketplace (Searching Mods)*
  - *Playing Minecraft* with instance name, loader badge, elapsed playtime, and supporter flair.

---

## System Requirements

| Component | Minimum | Recommended |
| :--- | :--- | :--- |
| **Operating System** | Windows 10 (64-bit) | Windows 10 / 11 (64-bit) |
| **Processor** | Intel Core i3 / AMD Ryzen 3 | Intel Core i5 / AMD Ryzen 5 or better |
| **Memory (RAM)** | 4 GB RAM | 8 GB – 16 GB RAM |
| **Graphics** | OpenGL 4.4 compatible GPU | Dedicated NVIDIA / AMD / Intel Arc GPU |
| **Java** | Built-in 1-Click Installer | JDK 8, 17, 21 or 25 |

---

## Installation & Quick Start

### For Players:
1. **Download** the latest release package from [GitHub Releases](https://github.com/hoanglonggg79/PhantomXLauncher/releases).
2. **Extract** the `.zip` archive to any directory.
3. **Launch** `PhantomX.exe` and enjoy!

> The `.zip` is a fully portable build — the Python backend ships inside it under `binaries/sidecar/`, so no separate Python installation is required.

### For Developers:

#### 1. Clone Repository
```bash
git clone https://github.com/hoanglonggg79/PhantomXLauncher.git
cd PhantomXLauncher
```

#### 2. Setup Python Sidecar
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r sidecar/requirements.txt
```
> Both files are required. `requirements.txt` covers the launcher core, while `sidecar/requirements.txt` adds the FastAPI / uvicorn / SSE stack the backend runs on.

#### 3. Setup Frontend
```bash
cd app
npm ci
```

#### 4. Run with Tauri Desktop Shell
```bash
# In the app/ directory
npm run tauri dev
```
> The Rust shell auto-spawns the backend from the repo (see `app/src-tauri/src/sidecar.rs`), so the virtualenv from step 2 must be active.

#### 5. Bump the App Version
```bash
python bump-version.py 1.2.1
```
> Writes the new version into every file that declares one — `scr/core.py` (`APP_VERSION`), `app/package.json`, `app/package-lock.json`, `app/src-tauri/Cargo.toml`, `app/src-tauri/tauri.conf.json`, `version.txt`, and the sidecar services. GitHub Actions runs this same script automatically on a `v*` tag, which keeps `APP_VERSION` in sync with `version.txt` so the in-app update checker behaves correctly.

---

## Technology Stack

- **Desktop Framework:** [Tauri 2](https://tauri.app/) (Rust)
- **Frontend:** [React 19](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), [Vite](https://vite.dev/)
- **Styling & Components:** [Tailwind CSS](https://tailwindcss.com/), [shadcn/ui](https://ui.shadcn.com/), [Lucide Icons](https://lucide.dev/)
- **State Management:** [Zustand](https://github.com/pmndrs/zustand)
- **Core Backend:** [Python 3.11+](https://www.python.org/), [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/)
- **Minecraft Core:** [minecraft-launcher-lib](https://gitlab.com/JakobDev/minecraft-launcher-lib)
- **Packaging:** [Nuitka](https://nuitka.net/)

---

## License

Distributed under the **GNU General Public License v3.0 (GPLv3)**. See [`LICENSE`](./LICENSE) for more information.

---

<div align="center">

Built for the Vietnam Minecraft community.  
**PhantomX Team** • [Join our Discord](https://discord.gg/PECavu2q4w) • [Report a Bug](https://github.com/hoanglonggg79/PhantomXLauncher/issues)

</div>
