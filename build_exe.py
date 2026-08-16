# -*- coding: utf-8 -*-
"""打包 WebJump 为单文件 exe（内嵌嵌入式 Python 运行时）。
用法：python build_exe.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
EMBED = os.path.join(ROOT, "embed_py")


def main():
    if not os.path.exists(os.path.join(EMBED, "python.exe")):
        sys.exit("缺少 embed_py 目录，请先准备嵌入式 Python（见对话说明）。")
    # 清理嵌入式环境里不需要的打包残留，减小体积
    for junk in ("get-pip.py",):
        p = os.path.join(EMBED, junk)
        if os.path.exists(p):
            os.remove(p)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--onefile", "--windowed", "--name", "WebJump",
           "--icon", os.path.join(ROOT, "app.ico"),
           "--add-data", EMBED + os.pathsep + "embed_py",
           "--distpath", os.path.join(ROOT, "dist"),
           "--workpath", os.path.join(ROOT, "build"),
           "--specpath", ROOT,
           os.path.join(ROOT, "webjump.py")]
    print("运行:", " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        sys.exit("打包失败，退出码 %s" % r.returncode)
    exe = os.path.join(ROOT, "dist", "WebJump.exe")
    print("打包完成:", exe, os.path.getsize(exe) // (1024 * 1024), "MB")


if __name__ == "__main__":
    main()
