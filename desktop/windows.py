import ctypes
import hashlib
import os
from ctypes import wintypes


class Mutex:

    def __init__(self, name):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.handle = self.kernel.CreateMutexW(None, False, "Local\\LiveSupport-" + name)
        self.acquired = bool(self.handle) and ctypes.get_last_error() != 183
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def instance_name(root):
    return hashlib.sha256(str(root.resolve()).lower().encode()).hexdigest()[:20]


class Job:
    """Kill all owned workers if the tray process exits or crashes."""

    def __init__(self):

        class Basic(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("min_ws", ctypes.c_size_t),
                ("max_ws", ctypes.c_size_t),
                ("active", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [(f"v{i}", ctypes.c_uint64) for i in range(6)]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", IO),
                ("process_mem", ctypes.c_size_t),
                ("job_mem", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        self.kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        self.kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.handle = self.kernel.CreateJobObjectW(None, None)
        info = Extended()
        info.basic.flags = 8192
        if not self.handle or not self.kernel.SetInformationJobObject(
            self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def add(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            process.kill()
            process.wait()
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def is_autostart_enabled(app_name: str = "LiveSupport") -> bool:
    """检查是否已设置开机自启动"""
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            winreg.QueryValueEx(key, app_name)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool, app_name: str = "LiveSupport") -> bool:
    """设置或取消开机自启动"""
    if os.name != "nt":
        return False
    import sys
    import winreg
    from pathlib import Path

    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                if getattr(sys, "frozen", False):
                    cmd = f'"{sys.executable}"'
                else:
                    entry = Path(__file__).resolve().parents[1] / "tray_app.py"
                    cmd = f'"{sys.executable}" "{entry}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
