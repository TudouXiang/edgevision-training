"""Birth identities are evidence, never authority to signal an arbitrary PID."""
from __future__ import annotations
import os
from pathlib import Path
from uuid import UUID


def boot_id() -> str | None:
    if os.name == "nt":
        return None  # Windows recovery requires a witnessed guardian drain receipt.
    return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()


def linux_identity(pid: int) -> dict | None:
    try:
        text = Path(f"/proc/{pid}/stat").read_bytes()
    except FileNotFoundError:
        return None
    fields = text[text.rfind(b")") + 2:].split()
    return {"pid": pid, "start_ticks": int(fields[19]), "session": int(fields[3]), "ppid": int(fields[1]), "state": fields[0].decode("ascii")}


def identity(pid: int) -> dict:
    if os.name == "nt":
        from .process_windows import process_identity
        return process_identity(pid)
    value = linux_identity(pid)
    if value is None:
        raise ProcessLookupError(pid)
    return {"platform": "linux", "pid": pid, "start_ticks": value["start_ticks"], "session": value["session"], "boot_id": boot_id()}


def valid_boot_id(value: object) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def valid_identity(record: object) -> bool:
    if not isinstance(record, dict) or type(record.get("pid")) is not int or not 0 < record["pid"] < 2**32:
        return False
    if record.get("platform") == "windows":
        return set(record) == {"platform", "pid", "creation_time"} and type(record.get("creation_time")) is int and 0 < record["creation_time"] < 2**64
    if record.get("platform") != "linux" or set(record) != {"platform", "pid", "start_ticks", "session", "boot_id"}:
        return False
    try:
        valid_boot = str(UUID(record["boot_id"])) == record["boot_id"]
    except (ValueError, TypeError, AttributeError):
        return False
    return valid_boot and all(type(record[key]) is int and record[key] > 0 for key in ("start_ticks", "session"))


def exited(record: dict) -> bool:
    """False means live or unverifiable. No signals are sent by recovery."""
    if not valid_identity(record):
        return False
    if os.name == "nt":
        from .process_windows import identity_exited
        return identity_exited(record)
    if record.get("platform") != "linux" or not isinstance(record.get("pid"), int) or not record.get("start_ticks") or not record.get("boot_id"):
        return False
    if record["boot_id"] != boot_id():
        return True
    current = linux_identity(record["pid"])
    return current is None or current["start_ticks"] != record["start_ticks"] or current["state"] == "Z"
