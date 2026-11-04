"""Typed Win32 Job Object containment; no Popen internals or taskkill fallback.

References: CreateProcessW / STARTUPINFOEXW / UpdateProcThreadAttribute,
Job Objects, JOBOBJECT_EXTENDED_LIMIT_INFORMATION, GetProcessTimes (Microsoft).
Only imported on Windows. All owned kernel handles are non-inheritable except
explicit stdin/stdout handles passed through PROC_THREAD_ATTRIBUTE_HANDLE_LIST.
"""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
import msvcrt
import os
import subprocess
from uuid import uuid4

kernel = C.WinDLL("kernel32", use_last_error=True)
SIZE_T = C.c_size_t
ULONG_PTR = C.c_size_t
HANDLE = W.HANDLE


class STARTUPINFO(C.Structure):
    _fields_ = [("cb", W.DWORD), ("lpReserved", W.LPWSTR), ("lpDesktop", W.LPWSTR), ("lpTitle", W.LPWSTR),
                ("dwX", W.DWORD), ("dwY", W.DWORD), ("dwXSize", W.DWORD), ("dwYSize", W.DWORD),
                ("dwXCountChars", W.DWORD), ("dwYCountChars", W.DWORD), ("dwFillAttribute", W.DWORD),
                ("dwFlags", W.DWORD), ("wShowWindow", W.WORD), ("cbReserved2", W.WORD), ("lpReserved2", C.POINTER(W.BYTE)),
                ("hStdInput", HANDLE), ("hStdOutput", HANDLE), ("hStdError", HANDLE)]


class STARTUPINFOEX(C.Structure):
    _fields_ = [("StartupInfo", STARTUPINFO), ("lpAttributeList", C.c_void_p)]


class PROCESS_INFORMATION(C.Structure):
    _fields_ = [("hProcess", HANDLE), ("hThread", HANDLE), ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD)]


class BASIC_LIMIT(C.Structure):
    _fields_ = [("PerProcessUserTimeLimit", C.c_int64), ("PerJobUserTimeLimit", C.c_int64), ("LimitFlags", W.DWORD),
                ("MinimumWorkingSetSize", SIZE_T), ("MaximumWorkingSetSize", SIZE_T), ("ActiveProcessLimit", W.DWORD),
                ("Affinity", ULONG_PTR), ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD)]


class IO_COUNTERS(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class EXTENDED_LIMIT(C.Structure):
    _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", SIZE_T),
                ("JobMemoryLimit", SIZE_T), ("PeakProcessMemoryUsed", SIZE_T), ("PeakJobMemoryUsed", SIZE_T)]


class BASIC_ACCOUNTING(C.Structure):
    _fields_ = [("TotalUserTime", C.c_int64), ("TotalKernelTime", C.c_int64), ("ThisPeriodTotalUserTime", C.c_int64),
                ("ThisPeriodTotalKernelTime", C.c_int64), ("TotalPageFaultCount", W.DWORD), ("TotalProcesses", W.DWORD),
                ("ActiveProcesses", W.DWORD), ("TotalTerminatedProcesses", W.DWORD)]


def api(name, restype, *argtypes):
    result = getattr(kernel, name)
    result.restype, result.argtypes = restype, list(argtypes)
    return result


CloseHandle = api("CloseHandle", W.BOOL, HANDLE)
CreateJobObjectW = api("CreateJobObjectW", HANDLE, C.c_void_p, W.LPCWSTR)
SetInformationJobObject = api("SetInformationJobObject", W.BOOL, HANDLE, C.c_int, C.c_void_p, W.DWORD)
QueryInformationJobObject = api("QueryInformationJobObject", W.BOOL, HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p)
TerminateJobObject = api("TerminateJobObject", W.BOOL, HANDLE, W.UINT)
InitializeProcThreadAttributeList = api("InitializeProcThreadAttributeList", W.BOOL, C.c_void_p, W.DWORD, W.DWORD, C.POINTER(SIZE_T))
UpdateProcThreadAttribute = api("UpdateProcThreadAttribute", W.BOOL, C.c_void_p, W.DWORD, ULONG_PTR, C.c_void_p, SIZE_T, C.c_void_p, C.c_void_p)
DeleteProcThreadAttributeList = api("DeleteProcThreadAttributeList", None, C.c_void_p)
CreateProcessW = api("CreateProcessW", W.BOOL, W.LPCWSTR, W.LPWSTR, C.c_void_p, C.c_void_p, W.BOOL, W.DWORD, C.c_void_p, W.LPCWSTR, C.POINTER(STARTUPINFOEX), C.POINTER(PROCESS_INFORMATION))
TerminateProcess = api("TerminateProcess", W.BOOL, HANDLE, W.UINT)
ResumeThread = api("ResumeThread", W.DWORD, HANDLE)
WaitForSingleObject = api("WaitForSingleObject", W.DWORD, HANDLE, W.DWORD)
GetExitCodeProcess = api("GetExitCodeProcess", W.BOOL, HANDLE, C.POINTER(W.DWORD))
OpenProcess = api("OpenProcess", HANDLE, W.DWORD, W.BOOL, W.DWORD)
GetProcessTimes = api("GetProcessTimes", W.BOOL, HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME))
IsProcessInJob = api("IsProcessInJob", W.BOOL, HANDLE, HANDLE, C.POINTER(W.BOOL))
GetCurrentProcess = api("GetCurrentProcess", HANDLE)
AssignProcessToJobObject = api("AssignProcessToJobObject", W.BOOL, HANDLE, HANDLE)


def checked(ok):
    if not ok:
        raise C.WinError(C.get_last_error())
    return ok


def creation_time(handle) -> int:
    times = [W.FILETIME() for _ in range(4)]
    checked(GetProcessTimes(handle, *(C.byref(value) for value in times)))
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime


def process_identity(pid: int) -> dict:
    handle = checked(OpenProcess(0x1000 | 0x100000, False, pid))
    try:
        return {"platform": "windows", "pid": pid, "creation_time": creation_time(handle)}
    finally:
        CloseHandle(handle)


def identity_exited(record: dict) -> bool:
    if record.get("platform") != "windows" or not isinstance(record.get("pid"), int) or not record.get("creation_time"):
        return False
    handle = OpenProcess(0x1000 | 0x100000, False, record["pid"])
    if not handle:
        return C.get_last_error() == 87  # ERROR_INVALID_PARAMETER: PID does not exist.
    try:
        return creation_time(handle) != record["creation_time"] or WaitForSingleObject(handle, 0) == 0
    except OSError:
        return False
    finally:
        CloseHandle(handle)


class ProcessTree:
    def __init__(self, command: list[str]):
        self.command = command
        self.job = None
        self.info = PROCESS_INFORMATION()
        self.output = None
        self.gate = None
        self.root_code = None
        self.record = None
        self.spawned = False
        self.member = False
        self.name = f"Local\\EdgeVision-{uuid4()}"
        C.set_last_error(0)
        self.job = checked(CreateJobObjectW(None, self.name))
        try:
            if C.get_last_error() == 183:
                raise RuntimeError("Job Object name already exists")
            limits = EXTENDED_LIMIT()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE, no breakaway.
            checked(SetInformationJobObject(self.job, 9, C.byref(limits), C.sizeof(limits)))
        except BaseException:
            CloseHandle(self.job)
            self.job = None
            raise

    def start(self) -> None:
        input_read, input_write = os.pipe()
        output_read, output_write = os.pipe()
        self.gate = os.fdopen(input_write, "wb", buffering=0)
        self.output = os.fdopen(output_read, "rb", buffering=0)
        size = SIZE_T()
        attribute_buffer = None
        initialized = False
        try:
            inherited = (HANDLE * 2)(msvcrt.get_osfhandle(input_read), msvcrt.get_osfhandle(output_write))
            for handle in inherited:
                os.set_handle_inheritable(handle, True)
            InitializeProcThreadAttributeList(None, 2, 0, C.byref(size))
            if C.get_last_error() != 122 or size.value == 0:
                raise C.WinError(C.get_last_error())
            attribute_buffer = C.create_string_buffer(size.value)
            checked(InitializeProcThreadAttributeList(attribute_buffer, 2, 0, C.byref(size)))
            initialized = True
            jobs = (HANDLE * 1)(self.job)
            checked(UpdateProcThreadAttribute(attribute_buffer, 0, 0x2000D, jobs, C.sizeof(jobs), None, None))  # JOB_LIST
            checked(UpdateProcThreadAttribute(attribute_buffer, 0, 0x20002, inherited, C.sizeof(inherited), None, None))  # HANDLE_LIST
            startup = STARTUPINFOEX()
            startup.StartupInfo.cb = C.sizeof(startup)
            startup.StartupInfo.dwFlags = 0x100  # STARTF_USESTDHANDLES
            startup.StartupInfo.hStdInput = inherited[0]
            startup.StartupInfo.hStdOutput = startup.StartupInfo.hStdError = inherited[1]
            startup.lpAttributeList = C.cast(attribute_buffer, C.c_void_p)
            command_line = C.create_unicode_buffer(subprocess.list2cmdline(self.command))
            checked(CreateProcessW(self.command[0], command_line, None, None, True, 0x00080000 | 0x4 | 0x08000000, None, None, C.byref(startup), C.byref(self.info)))
            self.spawned = True
            member = W.BOOL()
            checked(IsProcessInJob(self.info.hProcess, self.job, C.byref(member)))
            if not member.value:
                raise RuntimeError("Initial Job membership was not established")
            self.member = True
            self.record = {"platform": "windows", "pid": self.info.dwProcessId, "creation_time": creation_time(self.info.hProcess), "job_name": self.name}
        finally:
            if initialized:
                DeleteProcThreadAttributeList(attribute_buffer)
            os.close(input_read)
            os.close(output_write)

    def go(self) -> None:
        self.gate.write(b"GO\n")
        self.gate.close()
        if ResumeThread(self.info.hThread) == 0xFFFFFFFF:
            raise C.WinError(C.get_last_error())
        CloseHandle(self.info.hThread)
        self.info.hThread = None

    def poll(self) -> int | None:
        if self.info.hProcess and WaitForSingleObject(self.info.hProcess, 0) == 0:
            code = W.DWORD()
            checked(GetExitCodeProcess(self.info.hProcess, C.byref(code)))
            self.root_code = code.value
            CloseHandle(self.info.hProcess)
            self.info.hProcess = None
            if self.info.hThread:
                CloseHandle(self.info.hThread)
                self.info.hThread = None
        return self.root_code

    def empty(self) -> bool:
        self.poll()
        details = BASIC_ACCOUNTING()
        checked(QueryInformationJobObject(self.job, 1, C.byref(details), C.sizeof(details), None))
        return details.ActiveProcesses == 0 and (not self.spawned or self.root_code is not None)

    def stop(self, force: bool = False) -> None:
        checked(TerminateJobObject(self.job, 125))
        if self.spawned and not self.member and self.info.hProcess and self.poll() is None:
            checked(TerminateProcess(self.info.hProcess, 125))

    def close(self) -> None:
        for handle in (self.info.hThread, self.info.hProcess, self.job):
            if handle:
                CloseHandle(handle)
        self.info.hThread = self.info.hProcess = self.job = None
        for stream in (self.gate, self.output):
            if stream and not stream.closed:
                stream.close()
