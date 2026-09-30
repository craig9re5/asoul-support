"""Read-only process liveness checks for heartbeat lock files."""

import os


def is_process_running(pid: int) -> bool:
    """Check whether a PID exists without signaling or terminating it."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        process = kernel32.OpenProcess(4096, False, pid)
        if not process:
            return False
        try:
            exit_code = wintypes.DWORD()
            return (
                bool(kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code)))
                and exit_code.value == 259
            )
        finally:
            kernel32.CloseHandle(process)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
