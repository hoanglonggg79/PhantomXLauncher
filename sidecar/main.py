from __future__ import annotations

import sys
import socket
import secrets
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from loguru import logger

from sidecar import session
from sidecar.logging_config import configure_logging


def get_free_port() -> int:
    """
    Synchronously find a free port by binding to 127.0.0.1:0.
    The OS assigns an available port, which we extract and return.
    The socket is closed immediately, freeing the port for uvicorn.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def start_parent_watchdog(check_interval: float = 2.5) -> None:
    """
    Monitors the parent process (Tauri Shell).
    If the parent process terminates unexpectedly (Hard crash of Tauri)
    or PID is recycled, the sidecar self-terminates immediately.
    """
    import os
    import time
    import threading
    try:
        import psutil
    except ImportError:
        logger.warning("psutil not available, skipping parent process watchdog")
        return

    parent_pid = os.getppid()
    # Ignore watchdog if PID is invalid (e.g. 1 on Linux) or if running in explicit dev mode
    if parent_pid <= 1 or os.environ.get("PHANTOMX_DEV_MODE") == "1":
        logger.debug(f"Parent watchdog bypassed (parent_pid={parent_pid})")
        return

    try:
        parent_proc = psutil.Process(parent_pid)
        parent_name = parent_proc.name().lower()
        parent_create_time = parent_proc.create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logger.warning(f"Could not inspect parent process {parent_pid}: {e}")
        return

    # If started interactively in a developer terminal/IDE, don't self-terminate on terminal idle
    dev_parents = {"cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe", "code.exe", "py.exe", "python.exe", "conhost.exe"}
    if parent_name in dev_parents:
        logger.info(f"Sidecar started from dev environment ({parent_name}, pid={parent_pid}), watchdog running in permissive mode")
        return

    logger.info(f"Parent process watchdog started for PID {parent_pid} ({parent_name})")

    def _watchdog_loop():
        while True:
            time.sleep(check_interval)
            try:
                if not psutil.pid_exists(parent_pid):
                    logger.warning(f"Parent process {parent_pid} died. Terminating sidecar.")
                    os._exit(0)

                proc = psutil.Process(parent_pid)
                # Anti PID-recycling checks:
                # 1. Executable name must match
                # 2. Process creation time must match (prevents recycled PID to another process with same name)
                if proc.name().lower() != parent_name or abs(proc.create_time() - parent_create_time) > 1.0:
                    logger.warning(f"Parent PID {parent_pid} was recycled ({proc.name()} != {parent_name}). Terminating sidecar.")
                    os._exit(0)

                # Also if parent is zombie or dead
                if proc.status() in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
                    logger.warning(f"Parent process {parent_pid} is zombie/dead. Terminating sidecar.")
                    os._exit(0)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                logger.warning(f"Parent process {parent_pid} no longer accessible. Terminating sidecar.")
                os._exit(0)
            except Exception as e:
                logger.debug(f"Watchdog check warning: {e}")

    t = threading.Thread(target=_watchdog_loop, daemon=True, name="ParentWatchdog")
    t.start()


def main():
    """
    Find a free port, print handshake to stdout, then start uvicorn (blocking).
    """
    # Add project root to sys.path so 'sidecar' imports work from anywhere
    _SIDECAR_ROOT = Path(__file__).parent
    _PROJECT_ROOT = _SIDECAR_ROOT.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

    # Load .env BEFORE importing core_bridge (so CF_API_KEY is in os.environ)
    _SCR_ENV = _PROJECT_ROOT / "scr" / ".env"
    if _SCR_ENV.exists():
        load_dotenv(_SCR_ENV, override=True)

    # Logs live under %LOCALAPPDATA%\PhantomXTeam\PhantomX\logs, never next to the binary.
    _LOG_FILE = configure_logging()

    logger.info(f"PhantomX Sidecar starting - log: {_LOG_FILE}")

    # Watchdog monitors parent process and self-terminates if parent exits or PID is recycled
    start_parent_watchdog(2.5)

    # Ensure minecraft_launcher_lib does not attempt to read version.txt from disk in frozen standalone
    try:
        import minecraft_launcher_lib._helper as _mcll_helper
        import minecraft_launcher_lib.utils as _mcll_utils
        if getattr(_mcll_helper, "_user_agent_cache", None) is None:
            _mcll_helper._user_agent_cache = "minecraft-launcher-lib/8.0"
        if getattr(_mcll_utils, "_version_cache", None) is None:
            _mcll_utils._version_cache = "8.0"
    except Exception:
        pass

    # Generate secure session token (32 bytes = 64 hex chars)
    SESSION_TOKEN = secrets.token_hex(32)
    session.set_token(SESSION_TOKEN)
    logger.info(f"Generated session token: {SESSION_TOKEN[:16]}...{SESSION_TOKEN[-8:]}")

    PORT = get_free_port()
    logger.info(f"Allocated port: {PORT}")

    # Print handshake to stdout BEFORE uvicorn starts (this is the ONLY stdout line)
    print(f"PHANTOMX_READY:{PORT}:{SESSION_TOKEN}", flush=True)
    logger.info("Handshake sent to Tauri")

    # Start uvicorn (blocks indefinitely)
    try:
        from sidecar.app import create_app

        app = create_app()
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=PORT,
            log_level="info",
            log_config=None,
            access_log=False,
            reload=False,
        )
    except KeyboardInterrupt:
        logger.info("Sidecar shutting down (KeyboardInterrupt)")
    except Exception as e:
        logger.exception(f"Sidecar crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
