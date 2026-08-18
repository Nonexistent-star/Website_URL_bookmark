# -*- coding: utf-8 -*-
"""一键重建：先打包 WebJump.exe，再编译安装包 WebJump-Setup。
用法：python build_setup.py
注意：运行前请先关闭正在运行的 WebJump，否则 exe 无法覆盖。"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def find_py():
    """挑选第一个装有 PyInstaller 的 python 解释器。"""
    cands = []
    seen = set()
    for p in [sys.executable, shutil.which("python"), shutil.which("python3")]:
        if p and p not in seen:
            seen.add(p)
            cands.append(p)
    for d in os.environ.get("PATH", "").split(os.pathsep):
        for n in ("python.exe", "python3.exe"):
            fp = os.path.join(d, n)
            if os.path.exists(fp) and fp not in seen:
                seen.add(fp)
                cands.append(fp)
    for p in cands:
        try:
            r = subprocess.run([p, "-c", "import PyInstaller"], capture_output=True, timeout=60)
            if r.returncode == 0:
                return p
        except Exception:
            continue
    return sys.executable


PY = find_py()
ISCC = os.path.join(ROOT, "tools", "innosetup", "ISCC.exe")


def run(cmd):
    print(">>", " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        print("步骤失败:", cmd)
        sys.exit(r.returncode)


run([PY, os.path.join(ROOT, "build_exe.py")])
run([ISCC, os.path.join(ROOT, "WebJump-Setup.iss")])
print("安装包生成:", os.path.join(ROOT, "installer_out", "WebJump-Setup-1.1.0.exe"))
