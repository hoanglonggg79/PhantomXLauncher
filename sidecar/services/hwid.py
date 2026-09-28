"""
PhantomX Supporter Badge System — Hardware ID (HWID) Generator

Collects hardware identifiers on Windows (CPU, Motherboard, Disk),
combines them and produces a 1-way SHA-256 hash.

SECURITY & PRIVACY GUARANTEE:
- Raw hardware serial numbers and UUIDs are NEVER logged or transmitted over the network.
- Only the one-way SHA-256 hex digest is sent to the server.
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import winreg
from functools import lru_cache
from typing import Optional

from loguru import logger


def _run_powershell_cmd(cmd: str) -> str:
    """Run a fast PowerShell command and return stripped stdout."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception as e:
        logger.debug(f"PowerShell command '{cmd}' failed: {e}")
    return ""


def _get_cpu_id() -> str:
    """Retrieve CPU ProcessorId."""
    out = _run_powershell_cmd("(Get-CimInstance Win32_Processor).ProcessorId")
    if out:
        # Handle multiple sockets (multiline)
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        if lines:
            return lines[0]
    return ""


def _get_motherboard_uuid() -> str:
    """Retrieve Motherboard UUID or SerialNumber."""
    # Try ComputerSystemProduct UUID first
    uuid_out = _run_powershell_cmd("(Get-CimInstance Win32_ComputerSystemProduct).UUID")
    if uuid_out and uuid_out.strip() and "ffffffff" not in uuid_out.lower():
        return uuid_out.strip()

    # Fallback to BaseBoard SerialNumber
    board_out = _run_powershell_cmd("(Get-CimInstance Win32_BaseBoard).SerialNumber")
    if board_out and board_out.strip():
        return board_out.strip()

    return ""


def _get_disk_serial() -> str:
    """Retrieve OS Drive SerialNumber."""
    disk_out = _run_powershell_cmd(
        "(Get-CimInstance Win32_DiskDrive | Where-Object { $_.Index -eq 0 }).SerialNumber"
    )
    if disk_out and disk_out.strip():
        return disk_out.strip()
    return ""


def _get_machine_guid_registry() -> str:
    """Fallback: Read MachineGuid from Windows Registry."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            val, _ = winreg.QueryValueEx(key, "MachineGuid")
            if val and isinstance(val, str):
                return val.strip()
    except Exception as e:
        logger.debug(f"Registry MachineGuid read failed: {e}")
    return ""


@lru_cache(maxsize=1)
def get_hwid_hash() -> str:
    """
    Generate a deterministic, 1-way SHA-256 hash representing this machine.

    Cached in-memory so hardware inspection only runs once per sidecar process.
    Returns: 64-character lowercase hexadecimal SHA-256 string.
    """
    cpu = _get_cpu_id()
    board = _get_motherboard_uuid()
    disk = _get_disk_serial()
    reg_guid = _get_machine_guid_registry()

    # Ensure we have at least some distinguishing entropy
    raw_components = [
        cpu or "NO_CPU",
        board or "NO_BOARD",
        disk or "NO_DISK",
        reg_guid or "NO_REG",
    ]

    combined = "|".join(raw_components)
    hwid_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest().lower()

    logger.debug(f"Generated SHA-256 HWID: {hwid_hash[:8]}...{hwid_hash[-8:]}")
    return hwid_hash
