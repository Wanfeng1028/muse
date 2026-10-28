"""Windows-only read access, trusted process identity, and private output ACLs."""
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as w
import csv
import io
import os
from pathlib import Path
import subprocess
import sys
import uuid


def require_windows():
    if sys.platform != "win32" or c.sizeof(c.c_void_p) != 8:
        raise RuntimeError("Windows live capture requires 64-bit Python on Windows")


def sid_text(sid):
    advapi = c.WinDLL("advapi32", use_last_error=True)
    advapi.ConvertSidToStringSidW.argtypes = [c.c_void_p, c.POINTER(w.LPWSTR)]
    pointer = w.LPWSTR()
    if not advapi.ConvertSidToStringSidW(sid, c.byref(pointer)):
        raise RuntimeError("Could not determine the authorized Windows profile")
    try:
        return pointer.value
    finally:
        kernel = c.WinDLL("kernel32")
        kernel.LocalFree.argtypes = [c.c_void_p]
        kernel.LocalFree(pointer)


def profile_owner():
    require_windows()
    profile = Path(os.environ["USERPROFILE"])
    from snapshot_reader import _secure_existing_path
    profile = _secure_existing_path(profile, label="Windows profile", expected="directory")
    # A profile folder may be owned by Administrators. Match its registered SID
    # instead, including when a guest agent runs as SYSTEM for this profile.
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList") as profiles:
        index = 0
        while True:
            try:
                name = winreg.EnumKey(profiles, index)
            except OSError:
                break
            index += 1
            if not name.startswith("S-1-5-21-"):
                continue
            with winreg.OpenKey(profiles, name) as entry:
                registered = Path(os.path.expandvars(winreg.QueryValueEx(entry, "ProfileImagePath")[0]))
            if os.path.normcase(str(registered)) == os.path.normcase(str(profile)):
                return name
    raise RuntimeError("Could not match the authorized Windows profile SID")


def secure_output_root(path: Path):
    require_windows()
    from snapshot_reader import _secure_existing_path, _lexical_absolute
    path = _lexical_absolute(path)
    existing = path
    while not existing.exists():
        existing = existing.parent
    _secure_existing_path(existing, label="private vault ancestor", expected="directory")
    path.mkdir(parents=True, exist_ok=True)
    path = _secure_existing_path(path, label="private vault", expected="directory")
    sid = profile_owner()
    api = c.WinDLL("advapi32", use_last_error=True)
    api.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, c.POINTER(c.c_void_p), c.POINTER(w.ULONG)]
    api.GetSecurityDescriptorDacl.argtypes = [c.c_void_p, c.POINTER(w.BOOL), c.POINTER(c.c_void_p), c.POINTER(w.BOOL)]
    api.SetNamedSecurityInfoW.argtypes = [w.LPWSTR, w.DWORD, w.DWORD, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p]
    descriptor, dacl, present, defaulted = c.c_void_p(), c.c_void_p(), w.BOOL(), w.BOOL()
    sddl = f"D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)"
    if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, c.byref(descriptor), None):
        raise RuntimeError("Could not construct the private vault ACL")
    try:
        if not api.GetSecurityDescriptorDacl(descriptor, c.byref(present), c.byref(dacl), c.byref(defaulted)) or not present:
            raise RuntimeError("Could not read the private vault ACL")
        if api.SetNamedSecurityInfoW(str(path), 1, 4 | 0x80000000, None, None, dacl, None):
            raise RuntimeError("Could not protect the private vault ACL")
    finally:
        kernel = c.WinDLL("kernel32")
        kernel.LocalFree.argtypes = [c.c_void_p]
        kernel.LocalFree(descriptor)
    return path


class Guid(c.Structure):
    _fields_ = [("data1", w.DWORD), ("data2", w.WORD), ("data3", w.WORD), ("data4", c.c_ubyte * 8)]


def signed_binary(path: Path) -> bool:
    require_windows()
    class FileInfo(c.Structure):
        _fields_ = [("size", w.DWORD), ("path", w.LPCWSTR), ("handle", w.HANDLE), ("subject", c.c_void_p)]
    class TrustData(c.Structure):
        _fields_ = [("size", w.DWORD), ("policy", c.c_void_p), ("sip", c.c_void_p), ("ui", w.DWORD), ("revocation", w.DWORD), ("choice", w.DWORD), ("file", c.POINTER(FileInfo)), ("state_action", w.DWORD), ("state", w.HANDLE), ("url", w.LPCWSTR), ("flags", w.DWORD), ("ui_context", w.DWORD), ("settings", c.c_void_p)]
    action = Guid.from_buffer_copy(uuid.UUID("00aac56b-cd44-11d0-8cc2-00c04fc295ee").bytes_le)
    file = FileInfo(c.sizeof(FileInfo), str(path), None, None)
    data = TrustData()
    data.size, data.ui, data.choice, data.file, data.state_action, data.flags = c.sizeof(data), 2, 1, c.pointer(file), 1, 0x1000
    api = c.WinDLL("wintrust").WinVerifyTrust
    api.argtypes, api.restype = [w.HWND, c.POINTER(Guid), c.POINTER(TrustData)], w.LONG
    try:
        return api(w.HWND(-1), c.byref(action), c.byref(data)) == 0
    finally:
        data.state_action = 2
        api(w.HWND(-1), c.byref(action), c.byref(data))


def process_ids():
    require_windows()
    result = subprocess.run(["tasklist.exe", "/FI", "IMAGENAME eq Weixin.exe", "/FO", "CSV", "/NH"], capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    return sorted(int(row[1]) for row in csv.reader(io.StringIO(result.stdout.decode("utf-8", errors="replace"))) if len(row) >= 2 and row[0].casefold() == "weixin.exe" and row[1].isdigit())


class ProcessReader:
    def __init__(self, pid: int, allowed_owner: str):
        require_windows()
        self.kernel = c.WinDLL("kernel32", use_last_error=True)
        declarations = {
            "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "CloseHandle": ([w.HANDLE], w.BOOL),
            "ReadProcessMemory": ([w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)], w.BOOL),
            "VirtualQueryEx": ([w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t], c.c_size_t),
            "QueryFullProcessImageNameW": ([w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)], w.BOOL),
        }
        for name, (args, result) in declarations.items():
            method = getattr(self.kernel, name)
            method.argtypes, method.restype = args, result
        self.handle = self.kernel.OpenProcess(0x0010 | 0x0400, False, pid)
        if not self.handle:
            raise RuntimeError("The authorized Weixin.exe process cannot be read")
        try:
            buffer, size = c.create_unicode_buffer(32768), w.DWORD(32768)
            if not self.kernel.QueryFullProcessImageNameW(self.handle, 0, buffer, c.byref(size)):
                raise RuntimeError("Cannot identify the process executable")
            self.path = Path(buffer.value)
            if self.path.name.casefold() != "weixin.exe" or not signed_binary(self.path):
                raise RuntimeError("Process is not a Windows-trusted Weixin.exe")
            if self._owner() != allowed_owner:
                raise RuntimeError("Weixin.exe belongs to a different Windows profile")
        except BaseException:
            self.close()
            raise

    def _owner(self):
        api = c.WinDLL("advapi32", use_last_error=True)
        api.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
        api.GetTokenInformation.argtypes = [w.HANDLE, w.DWORD, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
        token = w.HANDLE()
        if not api.OpenProcessToken(self.handle, 8, c.byref(token)):
            raise RuntimeError("Cannot verify the Windows process owner")
        try:
            size = w.DWORD()
            api.GetTokenInformation(token, 1, None, 0, c.byref(size))
            buffer = c.create_string_buffer(size.value)
            if not api.GetTokenInformation(token, 1, buffer, size, c.byref(size)):
                raise RuntimeError("Cannot verify the Windows process owner")
            return sid_text(c.cast(buffer, c.POINTER(c.c_void_p))[0])
        finally:
            self.kernel.CloseHandle(token)

    def read(self, address, size):
        if not 0 < size <= 2 * 1024 * 1024:
            raise ValueError("Process read exceeds the chunk boundary")
        buffer, count = c.create_string_buffer(size), c.c_size_t()
        self.kernel.ReadProcessMemory(self.handle, c.c_void_p(address), buffer, size, c.byref(count))
        return buffer.raw[:count.value]

    def regions(self):
        class MBI(c.Structure):
            _fields_ = [("base", c.c_void_p), ("allocation", c.c_void_p), ("allocation_protect", w.DWORD), ("partition", w.WORD), ("size", c.c_size_t), ("state", w.DWORD), ("protect", w.DWORD), ("kind", w.DWORD)]
        address, result = 0, []
        while address < 0x800000000000:
            info = MBI()
            if not self.kernel.VirtualQueryEx(self.handle, c.c_void_p(address), c.byref(info), c.sizeof(info)):
                break
            if info.state == 0x1000 and info.protect & 0xFF in (2, 4, 8, 0x20, 0x40, 0x80) and not info.protect & 0x100:
                result.append((info.base, info.size))
            following = (info.base or 0) + info.size
            if following <= address:
                break
            address = following
        return result

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
