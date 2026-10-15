"""Live detector for the CMF Buds Pro 2 dial press-and-hold.

The hold makes the buds send the Bluetooth hands-free command "AT+BVRA=1"
(start voice recognition). Windows ignores it, but the Bluetooth stack logs
every raw packet to the Microsoft-Windows-BTH-BTHPORT ETW provider. We open a
real-time ETW session on that provider and scan each packet for the command.

Must run as admin (real-time ETW sessions need it). Ctrl+C to stop.
"""
import ctypes
import ctypes.wintypes as wt
import sys
import threading
import time
import uuid
from datetime import datetime

SESSION = "CMFDialHold"
BTHPORT = uuid.UUID("8a1f9517-3a8c-4a9e-a018-4f17a200f277")
NEEDLE = b"AT+BVRA="
DEBOUNCE_S = 1.0

advapi = ctypes.WinDLL("advapi32")
user32 = ctypes.WinDLL("user32")


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_uuid(cls, u):
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


class PROPS_WITH_NAME(ctypes.Structure):
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


EVENT_RECORD_CALLBACK = ctypes.WINFUNCTYPE(None, ctypes.c_void_p)


class EVENT_TRACE_LOGFILEW(ctypes.Structure):
    _fields_ = [("LogFileName", wt.LPWSTR), ("LoggerName", wt.LPWSTR), ("CurrentTime", ctypes.c_int64),
                ("BuffersRead", wt.ULONG), ("ProcessTraceMode", wt.ULONG), ("CurrentEvent", EVENT_TRACE),
                ("LogfileHeader", TRACE_LOGFILE_HEADER), ("BufferCallback", ctypes.c_void_p),
                ("BufferSize", wt.ULONG), ("Filled", wt.ULONG), ("EventsLost", wt.ULONG),
                ("EventRecordCallback", EVENT_RECORD_CALLBACK), ("IsKernelTrace", wt.ULONG), ("Context", ctypes.c_void_p)]


advapi.StartTraceW.argtypes = [ctypes.POINTER(ctypes.c_uint64), wt.LPCWSTR, ctypes.c_void_p]
advapi.ControlTraceW.argtypes = [ctypes.c_uint64, wt.LPCWSTR, ctypes.c_void_p, wt.ULONG]
advapi.EnableTraceEx2.argtypes = [ctypes.c_uint64, ctypes.POINTER(GUID), wt.ULONG, ctypes.c_ubyte,
                                  ctypes.c_uint64, ctypes.c_uint64, wt.ULONG, ctypes.c_void_p]
advapi.OpenTraceW.argtypes = [ctypes.POINTER(EVENT_TRACE_LOGFILEW)]
advapi.OpenTraceW.restype = ctypes.c_uint64
advapi.ProcessTrace.argtypes = [ctypes.POINTER(ctypes.c_uint64), wt.ULONG, ctypes.c_void_p, ctypes.c_void_p]
advapi.CloseTrace.argtypes = [ctypes.c_uint64]

EVENT_TRACE_CONTROL_STOP = 1
EVENT_TRACE_REAL_TIME_MODE = 0x100
WNODE_FLAG_TRACED_GUID = 0x20000
PROCESS_TRACE_MODE_REAL_TIME = 0x100
PROCESS_TRACE_MODE_EVENT_RECORD = 0x10000000
INVALID_TRACEHANDLE = 0xFFFFFFFFFFFFFFFF
# EVENT_RECORD layout (x64): EVENT_HEADER(80) + BUFFER_CONTEXT(4) + ExtCount(2) + UserDataLength(2) + ExtData(8) + UserData(8)
OFF_USERDATA_LEN, OFF_USERDATA = 86, 96


LOG = __file__.replace(".py", ".log")


def log(msg):
    line = f"{datetime.now():%H:%M:%S.%f}"[:-3] + "  " + msg
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def new_props():
    pw = PROPS_WITH_NAME()
    pw.p.Wnode.BufferSize = ctypes.sizeof(pw)
    pw.p.Wnode.Flags = WNODE_FLAG_TRACED_GUID
    pw.p.Wnode.ClientContext = 1  # QPC timestamps
    pw.p.LogFileMode = EVENT_TRACE_REAL_TIME_MODE
    pw.p.BufferSize = 64  # KB
    pw.p.MinimumBuffers = 4
    pw.p.MaximumBuffers = 16
    pw.p.FlushTimer = 1  # flush every second at worst
    pw.p.LoggerNameOffset = ctypes.sizeof(EVENT_TRACE_PROPERTIES)
    return pw


def stop_session():
    pw = new_props()
    advapi.ControlTraceW(0, SESSION, ctypes.byref(pw), EVENT_TRACE_CONTROL_STOP)


# ---------- action fired on hold ----------
def press_combo(*vks):
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, 2, 0)


def on_hold(arg):
    log(f"HOLD  AT+BVRA={arg}  -> Win+H (voice typing)")
    press_combo(0x5B, 0x48)  # LWin + H


# ---------- ETW plumbing ----------
_last_fire = 0.0


@EVENT_RECORD_CALLBACK
def on_event(rec):
    global _last_fire
    n = ctypes.c_ushort.from_address(rec + OFF_USERDATA_LEN).value
    ptr = ctypes.c_void_p.from_address(rec + OFF_USERDATA).value
    if not n or not ptr:
        return
    data = ctypes.string_at(ptr, n)
    i = data.find(NEEDLE)
    if i < 0:
        return
    now = time.monotonic()
    if now - _last_fire < DEBOUNCE_S:  # same packet can be logged more than once
        return
    _last_fire = now
    arg = data[i + len(NEEDLE):i + len(NEEDLE) + 1].decode(errors="replace")
    threading.Thread(target=on_hold, args=(arg,), daemon=True).start()


def main():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        sys.exit("Run as admin: real-time ETW needs it.")

    stop_session()  # clear a leftover session from a previous run
    handle = ctypes.c_uint64()
    pw = new_props()
    rc = advapi.StartTraceW(ctypes.byref(handle), SESSION, ctypes.byref(pw))
    if rc:
        sys.exit(f"StartTrace failed: {rc}")
    guid = GUID.from_uuid(BTHPORT)
    rc = advapi.EnableTraceEx2(handle.value, ctypes.byref(guid), 1, 5, 0, 0, 0, None)
    if rc:
        stop_session()
        sys.exit(f"EnableTraceEx2 failed: {rc}")

    lf = EVENT_TRACE_LOGFILEW()
    lf.LoggerName = SESSION
    lf.ProcessTraceMode = PROCESS_TRACE_MODE_REAL_TIME | PROCESS_TRACE_MODE_EVENT_RECORD
    lf.EventRecordCallback = on_event
    th = advapi.OpenTraceW(ctypes.byref(lf))
    if th == INVALID_TRACEHANDLE:
        stop_session()
        sys.exit(f"OpenTrace failed: {ctypes.GetLastError()}")

    t = threading.Thread(target=lambda: advapi.ProcessTrace(ctypes.byref(ctypes.c_uint64(th)), 1, None, None),
                         daemon=True)
    t.start()
    log("listening for dial hold (Ctrl+C to stop)")
    try:
        while t.is_alive():
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        advapi.CloseTrace(th)
        stop_session()
        log("stopped")


if __name__ == "__main__":
    main()
