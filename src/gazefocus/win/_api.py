"""Win32 prototypes used by GazeFocus, declared once.

Private `WinDLL` instances (with use_last_error) keep these argtypes from clashing with
any other module's `ctypes.windll` usage.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
LONG_PTR = ctypes.c_ssize_t
HMONITOR = wintypes.HANDLE
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
WINEVENTPROC = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("_pad", ctypes.c_byte * 32)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [
        ("usFlags", wintypes.USHORT),
        ("_pad", wintypes.USHORT),  # the union below is 4-byte aligned
        ("usButtonFlags", wintypes.USHORT),
        ("usButtonData", wintypes.USHORT),
        ("ulRawButtons", wintypes.ULONG),
        ("lLastX", wintypes.LONG),
        ("lLastY", wintypes.LONG),
        ("ulExtraInformation", wintypes.ULONG),
    ]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [
        ("MakeCode", wintypes.USHORT),
        ("Flags", wintypes.USHORT),
        ("Reserved", wintypes.USHORT),
        ("VKey", wintypes.USHORT),
        ("Message", wintypes.UINT),
        ("ExtraInformation", wintypes.ULONG),
    ]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def _proto(fn, restype, *argtypes):
    fn.restype, fn.argtypes = restype, list(argtypes)


H, U, W, L, B, D = wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.BOOL, wintypes.DWORD
_proto(user32.DefWindowProcW, LRESULT, H, U, W, L)
_proto(user32.RegisterClassW, wintypes.ATOM, ctypes.POINTER(WNDCLASSW))
_proto(user32.CreateWindowExW, H, D, wintypes.LPCWSTR, wintypes.LPCWSTR, D, ctypes.c_int, ctypes.c_int,
       ctypes.c_int, ctypes.c_int, H, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
_proto(user32.DestroyWindow, B, H)
_proto(user32.PostMessageW, B, H, U, W, L)
_proto(user32.PeekMessageW, B, ctypes.POINTER(wintypes.MSG), H, U, U, U)
_proto(user32.TranslateMessage, B, ctypes.POINTER(wintypes.MSG))
_proto(user32.DispatchMessageW, LRESULT, ctypes.POINTER(wintypes.MSG))
_proto(user32.RegisterRawInputDevices, B, ctypes.POINTER(RAWINPUTDEVICE), U, U)
_proto(user32.GetRawInputData, U, wintypes.HANDLE, U, wintypes.LPVOID, ctypes.POINTER(U), U)
_proto(user32.RegisterHotKey, B, H, ctypes.c_int, U, U)
_proto(user32.UnregisterHotKey, B, H, ctypes.c_int)
_proto(user32.GetForegroundWindow, H)
_proto(user32.SetForegroundWindow, B, H)
_proto(user32.BringWindowToTop, B, H)
_proto(user32.GetWindowThreadProcessId, D, H, ctypes.POINTER(D))
_proto(user32.AttachThreadInput, B, D, D, B)
_proto(user32.IsWindow, B, H)
_proto(user32.IsWindowVisible, B, H)
_proto(user32.IsIconic, B, H)
_proto(user32.IsHungAppWindow, B, H)
_proto(user32.GetClassNameW, ctypes.c_int, H, wintypes.LPWSTR, ctypes.c_int)
_proto(user32.InternalGetWindowText, ctypes.c_int, H, wintypes.LPWSTR, ctypes.c_int)
_proto(user32.GetWindowLongPtrW, LONG_PTR, H, ctypes.c_int)
_proto(user32.GetAncestor, H, H, U)
_proto(user32.EnumWindows, B, WNDENUMPROC, L)
_proto(user32.MonitorFromWindow, HMONITOR, H, D)
_proto(user32.MonitorFromPoint, HMONITOR, wintypes.POINT, D)
_proto(user32.GetMonitorInfoW, B, HMONITOR, ctypes.POINTER(MONITORINFOEXW))
_proto(user32.GetWindowRect, B, H, ctypes.POINTER(wintypes.RECT))
_proto(user32.GetCursorPos, B, ctypes.POINTER(wintypes.POINT))
_proto(user32.SetCursorPos, B, ctypes.c_int, ctypes.c_int)
_proto(user32.SendInput, U, U, ctypes.POINTER(INPUT), ctypes.c_int)
_proto(user32.GetAsyncKeyState, ctypes.c_short, ctypes.c_int)
_proto(user32.SetWinEventHook, wintypes.HANDLE, D, D, wintypes.HMODULE, WINEVENTPROC, D, D, D)
_proto(user32.UnhookWinEvent, B, wintypes.HANDLE)
_proto(user32.RegisterSuspendResumeNotification, wintypes.HANDLE, wintypes.HANDLE, D)
_proto(user32.UnregisterSuspendResumeNotification, B, wintypes.HANDLE)
_proto(kernel32.GetModuleHandleW, wintypes.HMODULE, wintypes.LPCWSTR)
_proto(kernel32.CreateMutexW, wintypes.HANDLE, wintypes.LPVOID, B, wintypes.LPCWSTR)
_proto(kernel32.CloseHandle, B, wintypes.HANDLE)
_proto(kernel32.GetCurrentThreadId, D)
_proto(kernel32.GetCurrentProcessId, D)
_proto(kernel32.GetSystemPowerStatus, B, ctypes.POINTER(SYSTEM_POWER_STATUS))
_proto(dwmapi.DwmGetWindowAttribute, ctypes.c_long, H, D, wintypes.LPVOID, D)
_proto(shell32.SHQueryUserNotificationState, ctypes.c_long, ctypes.POINTER(ctypes.c_int))
_proto(wtsapi32.WTSRegisterSessionNotification, B, H, D)
_proto(wtsapi32.WTSUnRegisterSessionNotification, B, H)
_proto(user32.SetWindowLongPtrW, LONG_PTR, H, ctypes.c_int, LONG_PTR)
_proto(user32.SetWindowDisplayAffinity, B, H, D)
_proto(user32.IsZoomed, B, H)
_proto(user32.GetDC, wintypes.HDC, H)
_proto(user32.ReleaseDC, ctypes.c_int, H, wintypes.HDC)
_proto(gdi32.CreateCompatibleDC, wintypes.HDC, wintypes.HDC)
_proto(gdi32.CreateDIBSection, wintypes.HBITMAP, wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER), U,
       ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, D)
_proto(gdi32.SelectObject, wintypes.HGDIOBJ, wintypes.HDC, wintypes.HGDIOBJ)
_proto(gdi32.BitBlt, B, wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HDC,
       ctypes.c_int, ctypes.c_int, D)
_proto(gdi32.DeleteObject, B, wintypes.HGDIOBJ)
_proto(gdi32.DeleteDC, B, wintypes.HDC)
_proto(dwmapi.DwmFlush, ctypes.c_long)
