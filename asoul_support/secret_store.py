"""User-scoped DPAPI on Windows; OS keyring elsewhere. No plaintext fallback."""

import base64
import ctypes
from ctypes import wintypes
import json
import os
import uuid

FORMAT = "livesupport-protected-credentials"


def is_envelope(value):
    return isinstance(value, dict) and value.get("format") == FORMAT


def _dpapi(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("当前系统无法解密 Windows 凭证，请重新登录")

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    operation.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    # UI_FORBIDDEN only: never use LOCAL_MACHINE (which broadens access).
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise RuntimeError("凭证保护失败，请使用原 Windows 用户登录或重新扫码")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        if result.pbData:
            ctypes.memset(result.pbData, 0, result.cbData)
            kernel32.LocalFree(result.pbData)


def _keyring():
    try:
        import keyring

        backend = keyring.get_keyring()
        module = type(backend).__module__
        if module not in {"keyring.backends.SecretService", "keyring.backends.macOS"}:
            raise RuntimeError("需要可用的系统凭据库，拒绝使用明文后端")
        return backend
    except ImportError:
        raise RuntimeError("请安装 asoul-support[secure-store] 并启用系统凭据库") from None


def seal(value):
    if not value:
        return {}
    payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
    if os.name == "nt":
        return {
            "format": FORMAT,
            "version": 1,
            "backend": "dpapi-user",
            "payload": base64.b64encode(_dpapi(payload)).decode("ascii"),
        }
    reference = str(uuid.uuid4())
    try:
        _keyring().set_password("LiveSupport", reference, payload.decode("utf-8"))
    except Exception:
        raise RuntimeError("系统凭据库保存失败，未回退到明文") from None
    return {"format": FORMAT, "version": 1, "backend": "os-keyring", "reference": reference}


def unseal(envelope):
    try:
        if envelope.get("version") != 1:
            raise ValueError()
        if envelope.get("backend") == "dpapi-user":
            raw = _dpapi(base64.b64decode(envelope["payload"], validate=True), decrypt=True)
        elif envelope.get("backend") == "os-keyring":
            raw = _keyring().get_password("LiveSupport", envelope["reference"])
            if raw is None:
                raise ValueError()
        else:
            raise ValueError()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except Exception:
        raise RuntimeError("无法读取受保护的凭证，请使用原系统用户或重新登录") from None


def discard(envelope):
    if is_envelope(envelope) and envelope.get("backend") == "os-keyring":
        try:
            _keyring().delete_password("LiveSupport", envelope["reference"])
        except Exception:
            raise RuntimeError("旧凭据库条目清理失败，请在系统凭据库中清理 LiveSupport") from None
