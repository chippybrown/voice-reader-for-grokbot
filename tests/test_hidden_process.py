# Every Windows program launch goes through hidden_process.
import ast
import os
import unittest

import hidden_process


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCH = {"Popen", "run", "call", "check_call", "check_output"}


def _direct_launches(path):
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source, filename=path)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in LAUNCH:
            continue
        owner = node.func.value
        if isinstance(owner, ast.Name) and owner.id == "subprocess":
            lines.append(node.lineno)
    return lines


class HiddenProcessTests(unittest.TestCase):
    def test_windows_launch_hides_the_console(self):
        kwargs = hidden_process.hidden_kwargs({"creationflags": 0x00000200}, windows=True)
        self.assertEqual(kwargs["creationflags"] & hidden_process.CREATE_NO_WINDOW, hidden_process.CREATE_NO_WINDOW)
        self.assertEqual(kwargs["creationflags"] & 0x00000200, 0x00000200)
        self.assertEqual(kwargs["creationflags"] & 0x00000008, 0)
        info = kwargs["startupinfo"]
        self.assertEqual(info.dwFlags & hidden_process.STARTF_USESHOWWINDOW, hidden_process.STARTF_USESHOWWINDOW)
        self.assertEqual(info.wShowWindow, hidden_process.SW_HIDE)
        same = {"stdin": None}
        self.assertIs(hidden_process.hidden_kwargs(same, windows=False), same)

    def test_every_windows_subprocess_uses_the_helper(self):
        offenders = []
        for dirpath, names, files in os.walk(ROOT):
            names[:] = [name for name in names if name not in ("tests", "packaging", ".git")]
            if os.path.basename(dirpath) in ("tests", "packaging"):
                continue
            for name in files:
                if not name.endswith(".py") or name == "hidden_process.py":
                    continue
                path = os.path.join(dirpath, name)
                for line in _direct_launches(path):
                    offenders.append("%s:%d" % (os.path.relpath(path, ROOT), line))
        self.assertEqual(offenders, [])
