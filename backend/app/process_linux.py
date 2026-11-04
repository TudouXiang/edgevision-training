"""Linux trusted-runner containment: subreaper plus identity-checked descendants."""
from __future__ import annotations
import ctypes
import os
from pathlib import Path
import signal
import subprocess

from .process_identity import identity, linux_identity


class ProcessTree:
    def __init__(self, command: list[str]):
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        libc.prctl.restype = ctypes.c_int
        if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise OSError(ctypes.get_errno(), "Cannot establish child subreaper")
        self.command = command
        self.child = None
        self.root_code = None
        self.output = None
        self.record = None

    def start(self) -> None:
        self.child = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)
        self.output = self.child.stdout
        self.record = identity(self.child.pid)

    def go(self) -> None:
        self.child.stdin.write(b"GO\n")
        self.child.stdin.flush()
        self.child.stdin.close()

    def poll(self) -> int | None:
        # This guardian is single-threaded for waitpid. Reap every adopted child.
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return self.root_code
            if pid == 0:
                return self.root_code
            if self.child and pid == self.child.pid:
                self.root_code = os.waitstatus_to_exitcode(status)
                self.child.returncode = self.root_code

    def empty(self) -> bool:
        self.poll()
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return True
        if pid and self.child and pid == self.child.pid:
            self.root_code = os.waitstatus_to_exitcode(status)
            self.child.returncode = self.root_code
        return False

    def stop(self, force: bool = False) -> None:
        # Only current direct children are signal targets. This main thread is
        # also the sole reaper: their PIDs cannot be reused during this selection.
        # When a parent dies, its descendants are adopted and handled next pass.
        descendants = []
        pids = set()
        children_interface = False
        for task in Path("/proc/self/task").iterdir():
            try:
                pids.update(int(value) for value in (task / "children").read_text().split())
                children_interface = True
            except FileNotFoundError:
                continue
        # Some kernels omit /proc/<pid>/task/<tid>/children (CONFIG_CHECKPOINT_RESTORE).
        # A flat ppid==self scan is safe here too: no multi-generation ancestry,
        # and this guardian has not reaped any selected child during the scan.
        if not children_interface:
            pids = {int(path.name) for path in Path("/proc").iterdir() if path.name.isdecimal()}
        for pid in pids:
            value = linux_identity(pid)
            if value is not None and value["ppid"] == os.getpid():
                descendants.append(value)
        for row in reversed(descendants):
            pidfd = None
            try:
                if hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"):
                    pidfd = os.pidfd_open(row["pid"])
                current = linux_identity(row["pid"])
                if current is None or current["start_ticks"] != row["start_ticks"]:
                    continue
                sig = signal.SIGKILL if force else signal.SIGTERM
                if pidfd is not None:
                    signal.pidfd_send_signal(pidfd, sig)
                else:
                    raise RuntimeError("pidfd signalling unavailable; cannot safely drain")
            except ProcessLookupError:
                pass
            finally:
                if pidfd is not None:
                    os.close(pidfd)

    def close(self) -> None:
        if self.child:
            for stream in (self.child.stdin, self.child.stdout):
                if stream and not stream.closed:
                    stream.close()
