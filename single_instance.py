# One running copy of Grokbot Voice. A second launch asks the first to
# come forward, then leaves. No Tk in this file.
import os
import sys
import threading


class InstanceLock:
    def __init__(self, directory):
        self.directory = directory
        self.path = os.path.join(directory, "instance.sock")
        self._sock = None
        self._mutex = None
        self._event = None

    def claim(self, on_focus):
        """Return True when this process should keep running.

        A False return means another copy is already up and has been asked
        to raise its window.
        """
        try:
            os.makedirs(self.directory, exist_ok=True)
        except OSError:
            return True
        if sys.platform == "win32":
            return self._claim_windows(on_focus)
        return self._claim_posix(on_focus)

    def _notify_posix(self):
        import socket
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.settimeout(1.0)
            client.connect(self.path)
            client.sendall(b"focus\n")
            return True
        except OSError:
            return False
        finally:
            client.close()

    def _claim_posix(self, on_focus):
        import socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        bound = False
        try:
            sock.bind(self.path)
            bound = True
        except OSError:
            if self._notify_posix():
                sock.close()
                return False
            try:
                os.remove(self.path)
            except OSError:
                pass
            try:
                sock.bind(self.path)
                bound = True
            except OSError:
                sock.close()
                return False
        if not bound:
            sock.close()
            return False
        sock.listen(1)
        self._sock = sock
        threading.Thread(target=self._serve, args=(sock, on_focus), name="instance-lock", daemon=True).start()
        return True

    def _serve(self, sock, on_focus):
        while self._sock is sock:
            try:
                conn, _addr = sock.accept()
            except OSError:
                return
            try:
                conn.recv(32)
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
            try:
                on_focus()
            except Exception:
                pass

    def _kernel(self):
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateEventW.restype = ctypes.c_void_p
        kernel.OpenEventW.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.OpenEventW.restype = ctypes.c_void_p
        kernel.SetEvent.argtypes = [ctypes.c_void_p]
        kernel.SetEvent.restype = ctypes.c_bool
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel.WaitForSingleObject.restype = ctypes.c_uint
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.GetLastError.restype = ctypes.c_ulong
        kernel.SetLastError.argtypes = [ctypes.c_ulong]
        return kernel

    def _signal_windows(self):
        kernel = self._kernel()
        handle = kernel.OpenEventW(0x0002, False, "Local\\GrokbotVoice.Focus")
        if not handle:
            return False
        kernel.SetEvent(handle)
        kernel.CloseHandle(handle)
        return True

    def _claim_windows(self, on_focus):
        kernel = self._kernel()
        kernel.SetLastError(0)
        handle = kernel.CreateMutexW(None, False, "Local\\GrokbotVoice.SingleInstance")
        if not handle:
            return True
        if kernel.GetLastError() == 183:
            self._signal_windows()
            kernel.CloseHandle(handle)
            return False
        self._mutex = handle
        event = kernel.CreateEventW(None, False, False, "Local\\GrokbotVoice.Focus")
        self._event = event
        if event:
            threading.Thread(target=self._wait_windows, args=(event, on_focus), name="instance-lock", daemon=True).start()
        return True

    def _wait_windows(self, event, on_focus):
        kernel = self._kernel()
        while self._event == event:
            if kernel.WaitForSingleObject(event, 500) != 0:
                continue
            try:
                on_focus()
            except Exception:
                pass

    def release(self):
        sock = self._sock
        self._sock = None
        self._event = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        try:
            os.remove(self.path)
        except OSError:
            pass
        if self._mutex and sys.platform == "win32":
            try:
                self._kernel().CloseHandle(self._mutex)
            except Exception:
                pass
            self._mutex = None
