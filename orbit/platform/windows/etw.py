"""Minimal real-time ETW consumer (ctypes, no deps). Needs admin.

    s = EtwSession("OrbitBT", provider_guid, on_payload=lambda data: ...)
    s.start()   # spawns the processing thread
    s.stop()
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import threading
import uuid
from typing import Callable

log = logging.getLogger("orbit.etw")
advapi = ctypes.WinDLL("advapi32")


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_uuid(cls, u: uuid.UUID):
        return cls.from_buffer_copy(u.bytes_le)


class WNODE_HEADER(ctypes.Structure):
    _fields_ = [("BufferSize", wt.ULONG), ("ProviderId", wt.ULONG), ("HistoricalContext", ctypes.c_uint64),
                ("TimeStamp", ctypes.c_int64), ("Guid", GUID), ("ClientContext", wt.ULONG), ("Flags", wt.ULONG)]


class EVENT_TRACE_PROPERTIES(ctypes.Structure):
    _fields_ = [("Wnode", WNODE_HEADER), ("BufferSize", wt.ULONG), ("MinimumBuffers", wt.ULONG),
                ("MaximumBuffers", wt.ULONG), ("MaximumFileSize", wt.ULONG), ("LogFileMode", wt.ULONG),
                ("FlushTimer", wt.ULONG), ("EnableFlags", wt.ULONG), ("AgeLimit", wt.LONG),
                ("NumberOfBuffers", wt.ULONG), ("FreeBuffers", wt.ULONG), ("EventsLost", wt.ULONG),
                ("BuffersWritten", wt.ULONG), ("LogBuffersLost", wt.ULONG), ("RealTimeBuffersLost", wt.ULONG),
                ("LoggerThreadId", wt.HANDLE), ("LogFileNameOffset", wt.ULONG), ("LoggerNameOffset", wt.ULONG)]


class _Props(ctypes.Structure):
    _fields_ = [("p", EVENT_TRACE_PROPERTIES), ("name", ctypes.c_wchar * 1024)]


class EVENT_TRACE_HEADER(ctypes.Structure):
    _fields_ = [("Size", wt.USHORT), ("FieldTypeFlags", wt.USHORT), ("Version", wt.ULONG), ("ThreadId", wt.ULONG),
                ("ProcessId", wt.ULONG), ("TimeStamp", ctypes.c_int64), ("Guid", GUID), ("ProcessorTime", ctypes.c_uint64)]


class EVENT_TRACE(ctypes.Structure):
    _fields_ = [("Header", EVENT_TRACE_HEADER), ("InstanceId", wt.ULONG), ("ParentInstanceId", wt.ULONG),
                ("ParentGuid", GUID), ("MofData", ctypes.c_void_p), ("MofLength", wt.ULONG), ("ClientContext", wt.ULONG)]


class SYSTEMTIME(ctypes.Structure):
    _fields_ = [(n, wt.WORD) for n in ("y", "mo", "dow", "d", "h", "mi", "s", "ms")]


class TIME_ZONE_INFORMATION(ctypes.Structure):
    _fields_ = [("Bias", wt.LONG), ("StandardName", ctypes.c_wchar * 32), ("StandardDate", SYSTEMTIME),
                ("StandardBias", wt.LONG), ("DaylightName", ctypes.c_wchar * 32), ("DaylightDate", SYSTEMTIME),
                ("DaylightBias", wt.LONG)]


class TRACE_LOGFILE_HEADER(ctypes.Structure):
    _fields_ = [("BufferSize", wt.ULONG), ("Version", wt.ULONG), ("ProviderVersion", wt.ULONG),
                ("NumberOfProcessors", wt.ULONG), ("EndTime", ctypes.c_int64), ("TimerResolution", wt.ULONG),
                ("MaximumFileSize", wt.ULONG), ("LogFileMode", wt.ULONG), ("BuffersWritten", wt.ULONG),
                ("LogInstanceGuid", GUID), ("LoggerName", ctypes.c_void_p), ("LogFileName", ctypes.c_void_p),
                ("TimeZone", TIME_ZONE_INFORMATION), ("BootTime", ctypes.c_int64), ("PerfFreq", ctypes.c_int64),
                ("StartTime", ctypes.c_int64), ("ReservedFlags", wt.ULONG), ("BuffersLost", wt.ULONG)]


RECORD_CB = ctypes.WINFUNCTYPE(None, ctypes.c_void_p)


class EVENT_TRACE_LOGFILEW(ctypes.Structure):
    _fields_ = [("LogFileName", wt.LPWSTR), ("LoggerName", wt.LPWSTR), ("CurrentTime", ctypes.c_int64),
                ("BuffersRead", wt.ULONG), ("ProcessTraceMode", wt.ULONG), ("CurrentEvent", EVENT_TRACE),
                ("LogfileHeader", TRACE_LOGFILE_HEADER), ("BufferCallback", ctypes.c_void_p),
                ("BufferSize", wt.ULONG), ("Filled", wt.ULONG), ("EventsLost", wt.ULONG),
                ("EventRecordCallback", RECORD_CB), ("IsKernelTrace", wt.ULONG), ("Context", ctypes.c_void_p)]


advapi.StartTraceW.argtypes = [ctypes.POINTER(ctypes.c_uint64), wt.LPCWSTR, ctypes.c_void_p]
advapi.ControlTraceW.argtypes = [ctypes.c_uint64, wt.LPCWSTR, ctypes.c_void_p, wt.ULONG]
advapi.EnableTraceEx2.argtypes = [ctypes.c_uint64, ctypes.POINTER(GUID), wt.ULONG, ctypes.c_ubyte,
                                  ctypes.c_uint64, ctypes.c_uint64, wt.ULONG, ctypes.c_void_p]
advapi.OpenTraceW.argtypes = [ctypes.POINTER(EVENT_TRACE_LOGFILEW)]
advapi.OpenTraceW.restype = ctypes.c_uint64
advapi.ProcessTrace.argtypes = [ctypes.POINTER(ctypes.c_uint64), wt.ULONG, ctypes.c_void_p, ctypes.c_void_p]
advapi.CloseTrace.argtypes = [ctypes.c_uint64]

_INVALID = 0xFFFFFFFFFFFFFFFF
# EVENT_RECORD (x64): EVENT_HEADER(80) + ETW_BUFFER_CONTEXT(4) + ExtendedDataCount(2) + UserDataLength(2)
#                     + ExtendedData*(8) + UserData*(8)
_OFF_LEN, _OFF_DATA = 86, 96


def is_admin() -> bool:
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


class EtwSession:
    def __init__(self, name: str, provider: uuid.UUID, on_payload: Callable[[bytes], None], level: int = 5):
        self.name, self.provider, self.on_payload, self.level = name, provider, on_payload, level
        self._handle = ctypes.c_uint64()
        self._trace = _INVALID
        self._cb = RECORD_CB(self._record)  # keep a reference: ctypes callbacks die with their wrapper

    def _props(self):
        pw = _Props()
        pw.p.Wnode.BufferSize = ctypes.sizeof(pw)
        pw.p.Wnode.Flags = 0x20000            # WNODE_FLAG_TRACED_GUID
        pw.p.Wnode.ClientContext = 1          # QPC clock
        pw.p.LogFileMode = 0x100              # EVENT_TRACE_REAL_TIME_MODE
        pw.p.BufferSize = 16                  # KB, small buffers flush sooner
        pw.p.MinimumBuffers = 4
        pw.p.MaximumBuffers = 32
        pw.p.FlushTimer = 1
        pw.p.LoggerNameOffset = ctypes.sizeof(EVENT_TRACE_PROPERTIES)
        return pw

    def _record(self, rec):
        n = ctypes.c_ushort.from_address(rec + _OFF_LEN).value
        ptr = ctypes.c_void_p.from_address(rec + _OFF_DATA).value
        if n and ptr:
            try:
                self.on_payload(ctypes.string_at(ptr, n))
            except Exception:
                log.exception("payload handler failed")

    def start(self):
        self._control_stop()  # leftover session from a crash
        pw = self._props()
        rc = advapi.StartTraceW(ctypes.byref(self._handle), self.name, ctypes.byref(pw))
        if rc:
            raise OSError(rc, f"StartTrace failed ({rc})")
        g = GUID.from_uuid(self.provider)
        rc = advapi.EnableTraceEx2(self._handle.value, ctypes.byref(g), 1, self.level, 0, 0, 0, None)
        if rc:
            self._control_stop()
            raise OSError(rc, f"EnableTraceEx2 failed ({rc})")
        lf = EVENT_TRACE_LOGFILEW()
        lf.LoggerName = self.name
        lf.ProcessTraceMode = 0x100 | 0x10000000  # REAL_TIME | EVENT_RECORD
        lf.EventRecordCallback = self._cb
        self._trace = advapi.OpenTraceW(ctypes.byref(lf))
        if self._trace == _INVALID:
            self._control_stop()
            raise OSError(ctypes.GetLastError(), "OpenTrace failed")
        h = ctypes.c_uint64(self._trace)
        threading.Thread(target=lambda: advapi.ProcessTrace(ctypes.byref(h), 1, None, None),
                         name=f"etw-{self.name}", daemon=True).start()

    def _control_stop(self):
        pw = self._props()
        advapi.ControlTraceW(0, self.name, ctypes.byref(pw), 1)  # EVENT_TRACE_CONTROL_STOP

    def stop(self):
        if self._trace != _INVALID:
            advapi.CloseTrace(self._trace)
            self._trace = _INVALID
        self._control_stop()
