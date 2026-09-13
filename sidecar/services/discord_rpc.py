from __future__ import annotations

import queue
import threading
import time
from typing import Any, Dict, List, Optional

from loguru import logger

DISCORD_CLIENT_ID = "1526783238406672475"
GITHUB_RELEASES_URL = "https://github.com/hoanglonggg79/MinecraftLauncher/releases"
DISCORD_INVITE_URL = "https://discord.gg/PECavu2q4w"
MIN_UPDATE_INTERVAL = 15.0  # s

DEFAULT_BUTTONS = [
    {"label": "Get PhantomX", "url": GITHUB_RELEASES_URL},
    {"label": "Join Discord", "url": DISCORD_INVITE_URL},
]

LOADER_ASSETS = {
    "fabric": ("loader_fabric", "Fabric Loader"),
    "forge": ("loader_forge", "Forge Loader"),
    "neoforge": ("loader_neoforge", "NeoForge Loader"),
    "vanilla": ("mc_vanilla", "Minecraft Vanilla"),
    "quilt": ("loader_fabric", "Quilt Loader"),
}


class DiscordRpcService:
    def __init__(self, client_id: str = DISCORD_CLIENT_ID):
        self.client_id = client_id
        self._rpc = None
        self._connected = False
        self._queue: queue.Queue = queue.Queue(maxsize=20)
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._last_update_time = 0.0
        self._current_state: Optional[Dict[str, Any]] = None
        self._game_start_time: Optional[int] = None
        self._enabled = True

    def start(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="DiscordRPCWorker",
        )
        self._worker_thread.start()
        logger.info("Discord RPC worker thread started")

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._queue.put_nowait({"action": "stop"})
        except Exception:
            pass
        if self._rpc:
            try:
                self._rpc.close()
            except Exception:
                pass
            self._connected = False

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled and self._rpc and self._connected:
            try:
                self._rpc.clear()
            except Exception:
                pass

    def update_presence(
        self,
        status: str,
        instance_name: Optional[str] = None,
        loader: Optional[str] = None,
        mc_version: Optional[str] = None,
        is_supporter: Optional[bool] = None,
    ) -> None:
        """Enqueue a status change for non-blocking asynchronous dispatch."""
        if not self._enabled:
            return
        payload = {
            "status": status.lower(),
            "instance_name": instance_name or "",
            "loader": (loader or "vanilla").lower(),
            "mc_version": mc_version or "",
            "is_supporter": bool(is_supporter),
            "timestamp": time.time(),
        }
        try:
            # Drain queue if backlog exists to prioritize newest state
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._queue.put_nowait(payload)
        except Exception as e:
            logger.debug(f"Could not enqueue Discord RPC update: {e}")

    def _ensure_connection(self) -> bool:
        if self._connected and self._rpc:
            return True
        try:
            from pypresence import Presence

            self._rpc = Presence(self.client_id)
            self._rpc.connect()
            self._connected = True
            logger.info("Connected to Discord IPC successfully")
            return True
        except Exception as e:
            logger.debug(f"Discord not running or connection failed: {e}")
            self._connected = False
            self._rpc = None
            return False

    def _build_payload(self, state: Dict[str, Any]) -> Dict[str, Any]:
        status = state.get("status", "idle")
        is_supporter = state.get("is_supporter", False)

        if status == "in_game":
            inst_name = state.get("instance_name", "Minecraft")
            loader_key = state.get("loader", "vanilla")
            mc_ver = state.get("mc_version", "")
            loader_asset, loader_label = LOADER_ASSETS.get(loader_key, ("mc_vanilla", "Minecraft"))

            if self._game_start_time is None:
                self._game_start_time = int(time.time())

            large_text = f"Minecraft {mc_ver} ({loader_label})" if mc_ver else f"Minecraft ({loader_label})"
            small_img = "badge_supporter" if is_supporter else loader_asset
            small_txt = "PhantomX Supporter ❤" if is_supporter else loader_label

            return {
                "details": "Đang chơi Minecraft",
                "state": f"Instance: {inst_name}",
                "large_image": "logo_phantomx",
                "large_text": large_text,
                "small_image": small_img,
                "small_text": small_txt,
                "start": self._game_start_time,
                "buttons": DEFAULT_BUTTONS,
            }

        # Reset game timer when returning to launcher
        self._game_start_time = None

        if status == "marketplace":
            return {
                "details": "Dạo quanh Marketplace",
                "state": "Đang tìm kiếm Mods",
                "large_image": "logo_phantomx",
                "large_text": "PhantomX Launcher v1.2.0",
                "buttons": DEFAULT_BUTTONS,
            }

        # Default: idle
        return {
            "details": "Browsing Launcher",
            "state": "v1.2.0 • Idle",
            "large_image": "logo_phantomx",
            "large_text": "PhantomX Launcher v1.2.0",
            "buttons": DEFAULT_BUTTONS,
        }

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=2.0)
            except queue.Empty:
                continue

            if item.get("action") == "stop":
                break

            if not self._enabled:
                continue

            now = time.time()
            # If same status and updated within rate limit window, throttle unless state changed
            state_changed = (
                self._current_state is None
                or self._current_state.get("status") != item.get("status")
                or self._current_state.get("instance_name") != item.get("instance_name")
            )

            if not state_changed and (now - self._last_update_time) < MIN_UPDATE_INTERVAL:
                time.sleep(1.0)
                continue

            if not self._ensure_connection():
                # Discord not open, wait a bit before attempting again
                time.sleep(5.0)
                continue

            try:
                rpc_kwargs = self._build_payload(item)
                self._rpc.update(**rpc_kwargs)
                self._last_update_time = time.time()
                self._current_state = item
                logger.debug(f"Discord RPC updated: {item.get('status')} -> {rpc_kwargs.get('details')}")
            except Exception as e:
                logger.debug(f"Error sending Discord RPC payload: {e}")
                self._connected = False
                self._rpc = None
                time.sleep(3.0)


# Singleton instance
_service: Optional[DiscordRpcService] = None
_lock = threading.Lock()


def get_discord_rpc_service() -> DiscordRpcService:
    global _service
    if _service is None:
        with _lock:
            if _service is None:
                _service = DiscordRpcService()
                _service.start()
    return _service
