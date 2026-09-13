from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from sidecar.services.core_service import get_core, get_manager, load_settings
from sidecar.services.tasks import TaskCancelled, TaskContext, start_task
from sidecar.utils.file_ops import (
    safe_copy,
    safe_copytree,
    safe_delete,
    safe_rename,
    safe_rmtree,
    safe_write_text,
)

NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
LOADERS = ("vanilla", "fabric", "forge", "quilt", "neoforge")
GAME_LOG_KEYWORDS = ("[CHAT]", "INFO", "WARN", "ERROR", "Exception", "Caused by")

CONFIG_NAME = "instance.json"

# Never worth cloning: regenerated on next launch, or noise from the source run.
CLONE_SKIP_ALWAYS = frozenset(
    {CONFIG_NAME, "logs", "crash-reports", "natives", ".fabric", ".mixin.out", "usercache.json"}
)
# Opt-out groups exposed by the Clone dialog (Update.md §4).
CLONE_SKIP_SAVES = frozenset({"saves"})
CLONE_SKIP_CONFIGS = frozenset(
    {"config", "options.txt", "optionsof.txt", "optionsshaders.txt", "shaderpacks",
     "resourcepacks", "servers.dat", "servers.dat_old"}
)
CLONE_SKIP_MODS = frozenset({"mods"})

# Subfolders the UI is allowed to reveal in the file manager.
OPENABLE_SUBDIRS = frozenset(
    {"mods", "saves", "config", "resourcepacks", "shaderpacks", "screenshots", "logs",
     "crash-reports"}
)

_processes: Dict[str, subprocess.Popen] = {}
_proc_lock = threading.Lock()


class InstanceError(Exception):
    """
    Bad request from the client: invalid name, unknown instance, or conflict.

    `status` lets a call site pin the HTTP code instead of leaving the API layer
    to infer it from the message text (see `api/instances.py:_fail`).
    """

    def __init__(self, message: str, *, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


def validate_name(name: str) -> str:
    """
    Instance names become directory names, so they are strictly whitelisted and the
    resolved path is confirmed to stay inside INST_DIR.
    """
    clean = (name or "").strip()
    if not NAME_PATTERN.match(clean) or clean in {".", ".."}:
        raise InstanceError(
            "Invalid name: use 1-64 chars from letters, digits, space, dot, dash, underscore"
        )

    inst_dir = Path(get_core().INST_DIR)
    resolved = (inst_dir / clean).resolve()
    if resolved.parent != inst_dir.resolve():
        raise InstanceError("Invalid name: path escapes the instances directory")
    return clean


def instances_root() -> Path:
    return Path(get_core().INST_DIR).resolve()


def assert_inside_instances(path: Path) -> Path:
    """
    Last line of defence for destructive operations. `game_dir` comes out of
    instance.json, so a hand-edited or corrupted config could otherwise point a
    delete/rename at an arbitrary directory.
    """
    root = instances_root()
    resolved = Path(path).resolve()
    if root not in resolved.parents:
        raise InstanceError(f"Refusing to touch a path outside the instances directory: {resolved}")
    return resolved


def instance_path(name: str) -> Path:
    """Canonical directory for `name`, derived from INST_DIR — never from game_dir."""
    return assert_inside_instances(instances_root() / validate_name(name))


def require_instance_dir(name: str) -> Tuple[str, Path]:
    """Validated name plus its directory, asserting the instance actually exists."""
    clean = validate_name(name)
    path = instance_path(clean)
    if not (path / CONFIG_NAME).is_file():
        raise InstanceError(f"Instance not found: {clean}")
    return clean, path


def save_instance(inst) -> None:
    """
    Persist instance.json through file_ops instead of `Instance.save()`, which
    writes directly with Path.write_text and would raise a bare PermissionError
    when the file is locked (RULE 3).
    """
    target = Path(inst.game_dir) / CONFIG_NAME
    payload = json.dumps(inst.to_dict(), indent=2, ensure_ascii=False)
    safe_write_text(target, payload, label="save instance.json").unwrap()


def _open_in_file_manager(path: Path) -> None:
    """Reveal `path` in the OS file manager. Raises OSError so the API can report it."""
    system = platform.system()
    if system == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def is_running(name: str) -> bool:
    with _proc_lock:
        proc = _processes.get(name)
    return proc is not None and proc.poll() is None


def serialize(inst) -> Dict[str, Any]:
    mgr = get_manager()
    try:
        installed = mgr.is_loader_installed(inst)
    except Exception:
        installed = False

    return {
        "name": inst.name,
        "version_id": inst.version_id,
        "loader": inst.loader,
        "loader_version": inst.loader_version,
        "game_dir": inst.game_dir,
        "created_at": getattr(inst, "created_at", ""),
        "last_played": getattr(inst, "last_played", ""),
        "play_count": getattr(inst, "play_count", 0),
        "notes": getattr(inst, "notes", ""),
        "mod_count": len(getattr(inst, "mods", []) or []),
        "installed": installed,
        "running": is_running(inst.name),
    }


def list_instances() -> List[Dict[str, Any]]:
    core = get_core()
    out: List[Dict[str, Any]] = []
    inst_dir = Path(core.INST_DIR)
    if not inst_dir.exists():
        return out

    for d in sorted(inst_dir.iterdir()):
        if not d.is_dir():
            continue
        cfg = d / "instance.json"
        if not cfg.exists():
            continue
        inst = core.Instance.load(cfg)
        if inst is None:
            logger.warning(f"Skipping unreadable instance: {cfg}")
            continue
        out.append(serialize(inst))
    return out


def get_instance(name: str):
    core = get_core()
    clean = validate_name(name)
    cfg = Path(core.INST_DIR) / clean / "instance.json"
    if not cfg.exists():
        raise InstanceError(f"Instance not found: {clean}")
    inst = core.Instance.load(cfg)
    if inst is None:
        raise InstanceError(f"Instance config unreadable: {clean}")
    return inst


def create_instance(
    name: str,
    version_id: str,
    loader: str = "vanilla",
    loader_version: str = "",
) -> Dict[str, Any]:
    """
    Write instance.json, then install the version and loader on a worker thread.
    Returns the new instance plus the task id to subscribe to.
    """
    core = get_core()
    clean = validate_name(name)

    loader = (loader or "vanilla").lower().strip()
    if loader not in LOADERS:
        raise InstanceError(f"Unknown loader: {loader}. Expected one of {', '.join(LOADERS)}")
    if not (version_id or "").strip():
        raise InstanceError("version_id is required")
    if (Path(core.INST_DIR) / clean / "instance.json").exists():
        raise InstanceError(f"Instance already exists: {clean}")

    inst = core.Instance(
        name=clean,
        version_id=version_id.strip(),
        loader=loader,
        loader_version=(loader_version or "").strip(),
    )
    save_instance(inst)
    logger.info(f"Instance created: {clean} ({inst.version_id}/{loader})")

    task_id = start_task(lambda ctx: _install(ctx, inst), name=f"install-{clean}")
    return {"instance": serialize(inst), "task_id": task_id}


def install_instance(name: str) -> Dict[str, Any]:
    """Re-run installation for an existing instance: repair, or finish a failed create."""
    inst = get_instance(name)
    task_id = start_task(lambda ctx: _install(ctx, inst), name=f"install-{inst.name}")
    return {"instance": serialize(inst), "task_id": task_id}


def _install(ctx: TaskContext, inst) -> Dict[str, Any]:
    mgr = get_manager()
    settings = load_settings()
    java_path = str(settings.get("java_path") or "")

    ctx.log(f"Installing Minecraft {inst.version_id} for '{inst.name}'")
    if not mgr.install_vanilla(
        inst.version_id, inst.game_dir, cb_progress=ctx.progress, cb_log=ctx.log
    ):
        raise RuntimeError(f"Failed to install Minecraft {inst.version_id}")

    if inst.loader != "vanilla":
        ctx.log(f"Installing {inst.loader} {inst.loader_version or '(latest)'}")
        from sidecar.services.java import resolve_java_executable
        java = resolve_java_executable(inst.version_id, java_path)
        if not java:
            java = mgr.find_java_for_version(inst.version_id) or mgr.find_java() or ""
        if java and java.lower().endswith("javaw.exe"):
            java = java[:-9] + "java.exe"

        if java:
            ctx.log(f"Using Java runtime: {java}")
        else:
            ctx.log("⚠️ No explicit Java runtime found. Attempting system PATH fallback.", level="warning")

        if inst.loader == "fabric":
            ok = mgr.install_fabric(
                inst.version_id, inst.loader_version, inst.game_dir, java_path=java, cb_log=ctx.log
            )
        elif inst.loader == "quilt":
            ok = mgr.install_quilt(
                inst.version_id, inst.loader_version, inst.game_dir, java_path=java, cb_log=ctx.log
            )
        elif inst.loader == "forge":
            forge_version = inst.loader_version
            if not forge_version:
                candidates = mgr.get_forge_versions(inst.version_id)
                if not candidates:
                    raise RuntimeError(f"No Forge build found for {inst.version_id}")
                forge_version = candidates[0]
                ctx.log(f"Resolved Forge version: {forge_version}")
            ok = mgr.install_forge(
                inst.version_id, forge_version, inst.game_dir, java, cb_log=ctx.log
            )
        else:
            if not inst.loader_version:
                raise RuntimeError("NeoForge requires an explicit loader_version")
            ok = mgr.install_neoforge(
                inst.version_id, inst.loader_version, inst.game_dir, java, cb_log=ctx.log
            )

        if not ok:
            raise RuntimeError(f"Failed to install {inst.loader} for {inst.version_id}")

    ctx.log(f"'{inst.name}' is ready to play")
    return {"instance": serialize(inst)}


def resolve_launch_version(inst) -> str:
    """
    Pick the modded version folder the loader installer produced, mirroring the
    resolution the legacy launcher does before building the command.
    """
    versions_dir = Path(inst.game_dir) / "versions"
    if not versions_dir.exists():
        return inst.version_id

    if inst.loader in ("fabric", "forge", "quilt", "neoforge"):
        keyword = inst.loader.lower()
        matches = [
            d.name
            for d in sorted(versions_dir.iterdir(), reverse=True)
            if d.is_dir() and keyword in d.name.lower() and inst.version_id in d.name
        ]
        if matches:
            return matches[0]

    return inst.version_id


def launch_instance(
    name: str,
    username: Optional[str] = None,
    ram: Optional[int] = None,
) -> Dict[str, Any]:
    inst = get_instance(name)
    if is_running(inst.name):
        raise InstanceError(f"'{inst.name}' is already running")

    settings = load_settings()
    auth_mode = str(settings.get("auth_mode") or "offline").lower()
    extra_jvm = str(settings.get("extra_jvm") or "")
    java_path = str(settings.get("java_path") or "")
    resolved_ram = int(ram or settings.get("ram") or 2048)

    session_uuid = ""
    session_token = ""

    if auth_mode == "elyby":
        from sidecar.services import elyby_auth, minecraft_runtime

        creds = elyby_auth.get_session_credentials()
        if not creds:
            raise InstanceError(
                "Chưa đăng nhập Ely.by. Mở Cài đặt → Tài khoản để đăng nhập.",
                status=401,
            )
        try:
            elyby_auth.refresh_session()
            creds = elyby_auth.get_session_credentials() or creds
        except Exception as e:
            logger.warning(f"Ely.by token refresh before launch failed: {e}")

        minecraft_runtime.ensure_authlib_injector()
        extra_jvm = minecraft_runtime.prepend_authlib_jvm(extra_jvm)
        resolved_user = creds["username"]
        session_uuid = creds["uuid"]
        session_token = creds["access_token"]
    else:
        resolved_user = (username or settings.get("username") or "Player").strip() or "Player"

    task_id = start_task(
        lambda ctx: _launch(
            ctx,
            inst,
            resolved_user,
            resolved_ram,
            extra_jvm,
            java_path,
            session_uuid,
            session_token,
        ),
        name=f"launch-{inst.name}",
    )
    return {"instance": serialize(inst), "task_id": task_id, "username": resolved_user}


def _launch(
    ctx: TaskContext,
    inst,
    username: str,
    ram: int,
    extra_jvm: str,
    java_path: str,
    session_uuid: str = "",
    session_token: str = "",
) -> Dict[str, Any]:
    mgr = get_manager()
    mgr.pre_launch_cleanup(inst.game_dir, cb_log=ctx.log)

    launch_vid = resolve_launch_version(inst)
    ctx.log(f"Launching '{inst.name}' ({launch_vid}) as {username}")
    ctx.progress(1, 4, "Building launch command")

    cmd = mgr.build_command(
        launch_vid,
        username,
        inst.game_dir,
        ram,
        extra_jvm,
        java_path,
        uuid=session_uuid,
        token=session_token,
    )

    kwargs: Dict[str, Any] = dict(
        cwd=inst.game_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    ctx.progress(2, 4, "Starting game process")
    proc = subprocess.Popen(cmd, **kwargs)
    with _proc_lock:
        _processes[inst.name] = proc

    ctx.log(f"Game started (pid {proc.pid})")
    ctx.progress(3, 4, "Game running")
    _touch_last_played(inst)

    # Update Discord RPC to in_game
    try:
        from sidecar.services.discord_rpc import get_discord_rpc_service
        from sidecar.services import supporter
        sup_status = supporter.get_supporter_status()
        is_sup = bool(sup_status.get("valid", False))
        loader = getattr(inst, "loader", "vanilla") or "vanilla"
        mc_ver = getattr(inst, "version_id", "") or ""
        get_discord_rpc_service().update_presence(
            status="in_game",
            instance_name=inst.name,
            loader=loader,
            mc_version=mc_ver,
            is_supporter=is_sup,
        )
    except Exception as e:
        logger.debug(f"Discord RPC in_game trigger warning: {e}")

    try:
        if proc.stdout is not None:
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip()
                if not line:
                    continue
                if any(k in line for k in GAME_LOG_KEYWORDS):
                    ctx.log(line)
                else:
                    logger.debug(f"MC: {line}")
        rc = proc.wait()
    finally:
        with _proc_lock:
            _processes.pop(inst.name, None)
        try:
            from sidecar.services.discord_rpc import get_discord_rpc_service
            get_discord_rpc_service().update_presence(status="idle")
        except Exception:
            pass

    ctx.progress(4, 4, "Game exited")
    ctx.log(f"Game exited with code {rc}")
    logger.info(f"Game exited: instance={inst.name} rc={rc}")
    return {"exit_code": rc, "instance": serialize(inst)}

def _touch_last_played(inst) -> None:
    from datetime import datetime

    try:
        inst.last_played = datetime.now().isoformat()
        inst.play_count = int(getattr(inst, "play_count", 0) or 0) + 1
        save_instance(inst)
    except Exception as e:
        logger.warning(f"Could not update last_played for {inst.name}: {e}")


def stop_instance(name: str) -> Dict[str, Any]:
    clean = validate_name(name)
    with _proc_lock:
        proc = _processes.get(clean)

    if proc is None or proc.poll() is not None:
        raise InstanceError(f"'{clean}' is not running")

    logger.info(f"Terminating game process for {clean} (pid {proc.pid})")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        logger.warning(f"Game process for {clean} force-killed")

    return {"name": clean, "stopped": True}


# ── Delete ──────────────────────────────────────────────────────────────────────


def delete_instance(name: str, delete_files: bool = False) -> Dict[str, Any]:
    """
    Two modes, matching the confirmation dialog:

    * `delete_files=False` — unlink instance.json only. The folder stays on disk
      but stops being a listable instance. One file, so it runs synchronously.
    * `delete_files=True` — wipe the whole directory. That is multi-GB work, so it
      goes through `start_task` and the caller follows `/api/events/{task_id}`.
    """
    clean, target = require_instance_dir(name)
    if is_running(clean):
        raise InstanceError(f"'{clean}' is running — stop the game before deleting it")

    if not delete_files:
        res = safe_delete(target / CONFIG_NAME, missing_ok=False, label="delete instance.json")
        if not res.ok:
            raise InstanceError(res.error or f"Could not remove '{clean}' from the list")
        logger.info(f"Instance removed from list, files kept: {clean}")
        return {
            "name": clean,
            "removed_from_list": True,
            "files_deleted": False,
            "path": str(target),
            "task_id": None,
        }

    task_id = start_task(lambda ctx: _delete_files(ctx, clean, target), name=f"delete-{clean}")
    return {
        "name": clean,
        "removed_from_list": True,
        "files_deleted": True,
        "path": str(target),
        "task_id": task_id,
    }


def _delete_files(ctx: TaskContext, clean: str, target: Path) -> Dict[str, Any]:
    assert_inside_instances(target)
    ctx.log(f"Deleting '{clean}' — {target}")

    # instance.json first: if a later step hits a locked file, whatever is left
    # behind is no longer a listable instance the user could try to launch.
    safe_delete(target / CONFIG_NAME, label="delete instance.json")

    entries = sorted(target.iterdir()) if target.is_dir() else []
    total = len(entries) + 1
    locked: List[str] = []

    for i, entry in enumerate(entries, start=1):
        ctx.check_cancelled()
        ctx.progress(i, total, f"Removing {entry.name}")
        res = safe_rmtree(entry) if entry.is_dir() else safe_delete(entry)
        if not res.ok:
            locked.append(entry.name)
            ctx.log(f"Could not remove {entry.name}: {res.error}", level="error")

    if locked:
        raise RuntimeError(
            f"{len(locked)} item(s) are locked and were left behind "
            f"({', '.join(locked[:5])}) — close Minecraft and try again"
        )

    ctx.progress(total, total, "Removing instance folder")
    safe_rmtree(target).unwrap()
    ctx.log(f"'{clean}' deleted")
    logger.info(f"Instance deleted with files: {clean}")
    return {"name": clean, "files_deleted": True}


# ── Clone ───────────────────────────────────────────────────────────────────────


def _clone_skip_set(copy_saves: bool, copy_configs: bool, copy_mods: bool) -> frozenset:
    skip = set(CLONE_SKIP_ALWAYS)
    if not copy_saves:
        skip |= CLONE_SKIP_SAVES
    if not copy_configs:
        skip |= CLONE_SKIP_CONFIGS
    if not copy_mods:
        skip |= CLONE_SKIP_MODS
    return frozenset(n.lower() for n in skip)


def _clone_worklist(src: Path, dest: Path, skip: frozenset) -> List[Tuple[Path, Path]]:
    """
    Flatten the copy into depth-2 units. Handing `assets/` to copytree in one call
    would be a single opaque multi-hundred-MB step: no progress, and Cancel would
    appear dead until it finished (RULE 1 — cancellation is cooperative).
    """
    work: List[Tuple[Path, Path]] = []
    for entry in sorted(src.iterdir()):
        lowered = entry.name.lower()
        if lowered in skip or lowered.endswith((".log", ".log.gz", ".tmp")):
            continue
        if entry.is_dir():
            try:
                children = sorted(entry.iterdir())
            except OSError as e:  # unreadable dir: copy it as one unit and let file_ops report
                logger.warning(f"clone: cannot list {entry}, copying wholesale: {e}")
                children = []
            if children:
                work.extend((child, dest / entry.name / child.name) for child in children)
            else:
                work.append((entry, dest / entry.name))
        else:
            work.append((entry, dest / entry.name))
    return work


def clone_instance(
    name: str,
    new_name: str,
    copy_saves: bool = True,
    copy_configs: bool = True,
    copy_mods: bool = True,
) -> Dict[str, Any]:
    """
    Duplicate an instance as a real physical copy — never a symlink or hardlink,
    so breaking the clone can never damage the original (Update.md §4).
    """
    clean, src = require_instance_dir(name)
    target_name = validate_name(new_name)
    if target_name.lower() == clean.lower():
        raise InstanceError(
            "The clone needs a name different from the source", status=409
        )

    dest = instance_path(target_name)
    if dest.exists():
        raise InstanceError(f"Instance already exists: {target_name}")
    if is_running(clean):
        raise InstanceError(f"'{clean}' is running — stop the game before cloning it")

    inst = get_instance(clean)
    skip = _clone_skip_set(copy_saves, copy_configs, copy_mods)
    task_id = start_task(
        lambda ctx: _clone(ctx, inst, src, target_name, dest, skip),
        name=f"clone-{clean}",
    )
    logger.info(
        f"Clone queued: {clean} → {target_name} "
        f"(saves={copy_saves} configs={copy_configs} mods={copy_mods})"
    )
    return {"source": clean, "name": target_name, "path": str(dest), "task_id": task_id}


def _clone(
    ctx: TaskContext, inst, src: Path, new_name: str, dest: Path, skip: frozenset
) -> Dict[str, Any]:
    core = get_core()
    assert_inside_instances(src)
    assert_inside_instances(dest)

    ctx.log(f"Cloning '{inst.name}' → '{new_name}' (physical copy)")
    work = _clone_worklist(src, dest, skip)
    total = len(work) + 1
    dest.mkdir(parents=True, exist_ok=True)

    try:
        for i, (source, target) in enumerate(work, start=1):
            ctx.check_cancelled()
            ctx.progress(i, total, f"Copying {source.relative_to(src)}")
            res = safe_copytree(source, target) if source.is_dir() else safe_copy(source, target)
            if not res.ok:
                raise RuntimeError(f"Copy failed at {source.relative_to(src)}: {res.error}")
    except Exception:
        # A half-copied directory would list as a broken instance; roll it back.
        ctx.log("Rolling back the partial clone", level="warning")
        safe_rmtree(dest)
        raise

    clone = core.Instance(
        name=new_name,
        version_id=inst.version_id,
        loader=getattr(inst, "loader", "vanilla"),
        loader_version=getattr(inst, "loader_version", ""),
        game_dir=str(dest),
    )
    clone.notes = getattr(inst, "notes", "")
    clone.mods = [] if "mods" in skip else list(getattr(inst, "mods", []) or [])
    clone.last_played = ""
    clone.play_count = 0

    ctx.progress(total, total, "Writing instance.json")
    save_instance(clone)
    ctx.log(f"Clone ready: '{new_name}'")
    logger.info(f"Instance cloned: {inst.name} → {new_name} ({len(work)} items)")
    return {"instance": serialize(clone), "source": inst.name, "items_copied": len(work)}


# ── Rename / edit ───────────────────────────────────────────────────────────────


def update_instance(
    name: str, new_name: Optional[str] = None, notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Edit the title and/or notes. Renaming moves the directory, which on one volume
    is an atomic metadata operation — fast enough to answer synchronously.
    """
    clean, src = require_instance_dir(name)
    inst = get_instance(clean)
    changed: List[str] = []

    requested = (new_name or "").strip()
    if requested and requested != clean:
        target_name = validate_name(requested)
        dest = instance_path(target_name)
        if dest.exists():
            raise InstanceError(f"Instance already exists: {target_name}")
        if is_running(clean):
            raise InstanceError(f"'{clean}' is running — stop the game before renaming it")

        res = safe_rename(src, dest, label="rename instance folder")
        if not res.ok:
            raise InstanceError(res.error or f"Could not rename '{clean}'")
        inst.name = target_name
        inst.game_dir = str(dest)
        changed.append("name")
        logger.info(f"Instance renamed: {clean} → {target_name}")

    if notes is not None:
        inst.notes = notes
        changed.append("notes")

    if changed:
        save_instance(inst)
    return {"instance": serialize(inst), "changed": changed}


def open_instance_folder(name: str, subdir: str = "") -> Dict[str, Any]:
    """Reveal the instance directory (or one whitelisted subfolder) in the file manager."""
    clean, target = require_instance_dir(name)

    wanted = (subdir or "").strip().lower()
    if wanted:
        if wanted not in OPENABLE_SUBDIRS:
            raise InstanceError(f"Unsupported subfolder: {subdir}")
        target = target / wanted
        target.mkdir(parents=True, exist_ok=True)

    assert_inside_instances(target)
    try:
        _open_in_file_manager(target)
    except OSError as e:
        raise InstanceError(f"Could not open the folder: {e}") from e

    logger.info(f"Opened folder for {clean}: {target}")
    return {"name": clean, "path": str(target), "opened": True}
