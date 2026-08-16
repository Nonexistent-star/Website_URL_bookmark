# -*- coding: utf-8 -*-
"""
网站快速跳转程序 WebJump
- 主页面 1000x640，左侧导航：列表 / 设置 / 添加 / 分类
- 列表：网站名称 | 网站URL(点击跳转) | 延迟 | 标签 | 跳转次数 | 打开方式
- 延迟：真实 ICMP ping；绿<=300ms，黄>300ms，红>=2000ms 或超时
- 设置：主题预设 + 每个块的颜色/字体颜色自定义、开机自启动、导出列表、默认打开方式
- 内置浏览器：Edge WebView2(Chromium 内核)，必应引擎，注入地址栏工具条
依赖：pip install pywebview
"""
import os
import re
import sys
import json
import time
import shutil
import socket
import subprocess
import threading
import webbrowser
import http.server
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, quote

import webview

APP_NAME = "WebJumpLauncher"
BING_HOME = "https://www.bing.com"
BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
DATA_FILE = os.path.join(BASE_DIR, "webjump_data.json")   # 仅存主题等配置
SITES_FILE = os.path.join(BASE_DIR, "网站列表.txt")        # 网站列表外置，便于迁移

# ---------------------------------------------------------------- 数据
DEFAULT_THEME = {
    "bg": "#f5f6fa", "side_bg": "#cfe3f7", "side_fg": "#23415e",
    "head_bg": "#f2d0cb", "head_fg": "#8a3324",
    "name_bg": "#b8dcec", "name_fg": "#123c55", "url_bg": "#9fd3e8", "url_fg": "#0d3b52",
    "tag_bg": "#c9ccd4", "tag_fg": "#2f3237", "count_bg": "#6f5b9e", "count_fg": "#ffffff",
    "open_bg": "#6d8f62", "open_fg": "#ffffff", "accent": "#3f7fbf",
}
DEFAULT_CONFIG = {"theme": dict(DEFAULT_THEME), "default_open": "system"}


def _default_data():
    return {"sites": [], "config": json.loads(json.dumps(DEFAULT_CONFIG))}


TXT_HEADER = [
    "# WebJump 网站列表（每行一个网站，保存后程序内点击“重新读取”或重启生效）",
    "# 格式：名称 | URL | 标签 | 打开方式 | 跳转次数",
    "# 打开方式可填：global(跟随全局设置) / system(系统默认浏览器) / builtin(内置浏览器) / edge / chrome / firefox",
    "# 以 # 开头的行为注释；也可直接增删行来批量管理网站。",
]


def _parse_sites_txt(text):
    sites, nid = [], 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2 or not parts[1]:
            continue
        nid += 1
        try:
            count = int(parts[4]) if len(parts) > 4 and parts[4] else 0
        except ValueError:
            count = 0
        sites.append({"id": nid, "name": parts[0] or "未命名",
                      "url": normalize_url(parts[1]),
                      "tag": (parts[2] if len(parts) > 2 and parts[2] else "未分类"),
                      "open": (parts[3] if len(parts) > 3 and parts[3] else "global"),
                      "count": count})
    return sites


def _write_sites_txt(sites):
    lines = list(TXT_HEADER)
    for s in sites:
        lines.append("%s | %s | %s | %s | %d" % (s["name"], s["url"], s["tag"], s["open"], s.get("count", 0)))
    tmp = SITES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, SITES_FILE)


def _migrate_legacy(d):
    """旧版本列表存在 json 里，迁移到外置 txt 并从 json 移除。"""
    if d.get("sites"):
        _write_sites_txt(d["sites"])
    d.pop("sites", None)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"config": d["config"]}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def load_data():
    d = None
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            d.setdefault("config", json.loads(json.dumps(DEFAULT_CONFIG)))
        except Exception:
            d = None
    if d is None:
        d = _default_data()
    d["config"].setdefault("theme", dict(DEFAULT_THEME))
    d["config"]["theme"].update({k: v for k, v in DEFAULT_THEME.items() if k not in d["config"]["theme"]})
    d["config"].setdefault("default_open", "system")
    if "sites" in d:                      # 旧版 json 内嵌列表 → 迁移
        _migrate_legacy(d)
    if os.path.exists(SITES_FILE):
        try:
            with open(SITES_FILE, "r", encoding="utf-8-sig") as f:
                d["sites"] = _parse_sites_txt(f.read())
        except Exception:
            d["sites"] = []
    else:
        d["sites"] = []
        _write_sites_txt([])              # 首次使用：生成空白模板文件
    return d


def save_data():
    global DATA_REV
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"config": DATA["config"]}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)
    _write_sites_txt(DATA["sites"])
    DATA_REV += 1


DATA_REV = 0

# ---------------------------------------------------------------- 浏览器探测
def _reg_app_path(name):
    import winreg
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for wow in ("", "WOW6432Node\\"):
            try:
                key = winreg.OpenKey(hive, wow + r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths" + "\\" + name)
                val, _ = winreg.QueryValueEx(key, "")
                winreg.CloseKey(key)
                if val and os.path.exists(val):
                    return val
            except OSError:
                continue
    return None


def find_browsers():
    out = {}
    edge = _reg_app_path("msedge.exe")
    if not edge:
        for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                  os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\Edge\Application\msedge.exe")):
            if p and os.path.exists(p):
                edge = p
                break
    out["edge"] = edge
    chrome = _reg_app_path("chrome.exe")
    if not chrome:
        for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                  os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe")):
            if p and os.path.exists(p):
                chrome = p
                break
    out["chrome"] = chrome
    ff = _reg_app_path("firefox.exe")
    if not ff:
        for p in (r"C:\Program Files\Mozilla Firefox\firefox.exe",
                  r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"):
            if os.path.exists(p):
                ff = p
                break
    out["firefox"] = ff
    return out


BROWSERS = find_browsers()
OPEN_LABEL = {"global": "跟随全局", "system": "系统默认浏览器", "builtin": "内置浏览器",
              "edge": "Edge浏览器", "chrome": "Chrome浏览器", "firefox": "Firefox浏览器"}

# ---------------------------------------------------------------- 功能函数
def normalize_url(url):
    url = (url or "").strip()
    if not url:
        return url
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    return url


DATA = load_data()

# ---------------------------------------------------------------- 本地监听服务（供 Edge 扩展 web-kz 提交收藏）
KZ_PORT = 47811
KZ_ALLOWED_OPEN = ("global", "system", "builtin", "edge", "chrome", "firefox")


class _KzHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def do_GET(self):
        if self.path.startswith("/wjkz/ping"):
            self._send(200, {"ok": True, "app": "WebJump"})
        elif self.path.startswith("/wjkz/tags"):
            self._send(200, {"tags": sorted({s["tag"] for s in DATA["sites"]})})
        else:
            self._send(404, {"ok": False})

    def do_POST(self):
        if not self.path.startswith("/wjkz/add"):
            self._send(404, {"ok": False})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            item = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            self._send(400, {"ok": False, "msg": "bad json"})
            return
        url = normalize_url(item.get("url") or "")
        host = urlparse(url).hostname or ""
        if not url or "." not in host:
            self._send(400, {"ok": False, "msg": "bad url"})
            return
        openm = item.get("open") or "global"
        if openm not in KZ_ALLOWED_OPEN:
            openm = "global"
        name = (item.get("name") or item.get("title") or "").strip() or host
        site = Api().add_site({"name": name, "url": url,
                               "tag": (item.get("tag") or "").strip() or "未分类",
                               "open": openm})
        self._send(200, {"ok": True, "id": site["id"]})

    def log_message(self, *args):
        pass


def start_local_server():
    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", KZ_PORT), _KzHandler)
    except OSError:
        return None          # 端口被占用（已有实例在监听）则跳过
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _host_of(url):
    try:
        return urlparse(normalize_url(url)).hostname or urlparse(url).hostname
    except Exception:
        return None


def _probe_icmp(url, timeout_ms):
    """方法1：真实 ICMP ping（部分网站/网关禁 ping，不通则交给后续方法）"""
    host = _host_of(url)
    if not host:
        return None
    try:
        proc = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout_ms), host],
            capture_output=True, text=True, timeout=timeout_ms / 1000 + 3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        m = re.search(r"[=<]\s*(\d+)\s*ms", proc.stdout)
        if proc.returncode == 0 and m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def _probe_tcp(url, timeout_ms):
    """方法2：TCP 连接测试（按 443/80 端口握手计时）"""
    host = _host_of(url)
    if not host:
        return None
    scheme = urlparse(normalize_url(url)).scheme
    ports = [80, 443] if scheme == "http" else [443, 80]
    for port in ports:
        try:
            t0 = time.perf_counter()
            with socket.create_connection((host, port), timeout=timeout_ms / 1000):
                return int((time.perf_counter() - t0) * 1000)
        except Exception:
            continue
    return None


def _probe_http(url, timeout_ms):
    """方法3：HTTP 请求测试（GET 首页并读取少量数据的响应耗时）"""
    try:
        import urllib.request
        req = urllib.request.Request(normalize_url(url),
                                     headers={"User-Agent": "Mozilla/5.0 (WebJumpProbe)"})
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout_ms / 1000) as r:
            r.read(2048)
        return int((time.perf_counter() - t0) * 1000)
    except Exception:
        return None


PROBERS = (("ping", _probe_icmp), ("tcp", _probe_tcp), ("http", _probe_http))


def ping_host(url, timeout_ms=2000):
    """延迟测试：依次用 ICMP ping / TCP 连接 / HTTP 请求各试一次，
    哪个方法先通就用它的延迟；全部不通才返回 None(超时)。
    返回 {"ms": 毫秒, "m": 方法名} 或 None。"""
    for name, fn in PROBERS:
        ms = fn(url, timeout_ms)
        if ms is not None:
            return {"ms": ms, "m": name}
    return None


def resolve_open_method(site):
    method = site.get("open", "global")
    if method == "global":
        method = DATA["config"].get("default_open", "system")
    return method


def open_url_with(method, url):
    if method == "builtin":
        open_builtin(url)
    elif method in ("edge", "chrome", "firefox") and BROWSERS.get(method):
        subprocess.Popen([BROWSERS[method], url],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        webbrowser.open(url)

# ---------------------------------------------------------------- 开机自启动
def autostart_cmd():
    if getattr(sys, "frozen", False):
        return '"%s"' % sys.executable
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    interp = pyw if os.path.exists(pyw) else sys.executable
    return '"%s" "%s"' % (interp, os.path.abspath(__file__))


def get_autostart():
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")
        try:
            winreg.QueryValueEx(key, APP_NAME)
            return True
        except OSError:
            return False
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


def set_autostart(enabled):
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                         0, winreg.KEY_SET_VALUE)
    try:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, autostart_cmd())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except OSError:
                pass
    finally:
        winreg.CloseKey(key)
    return get_autostart()

# ---------------------------------------------------------------- 内置浏览器
TOOLBAR_JS = r"""
(function(){
  function syncAddr(){var i=document.getElementById('wj-addr');if(i&&document.activeElement!==i)i.value=location.href;}
  if(document.getElementById('wj-bar')){syncAddr();return;}
  var bar=document.createElement('div');bar.id='wj-bar';
  bar.style.cssText='position:fixed;top:0;left:0;right:0;height:44px;z-index:2147483647;background:#1f2733;display:flex;align-items:center;gap:6px;padding:0 8px;box-sizing:border-box;font:13px/1 "Microsoft YaHei",sans-serif;';
  bar.innerHTML='<button id="wj-back" style="min-width:30px">←</button><button id="wj-fwd" style="min-width:30px">→</button><button id="wj-re" style="min-width:30px">⟳</button><button id="wj-home">必应</button>'
    +'<input id="wj-addr" style="flex:1;height:28px;border:1px solid #3a4656;border-radius:4px;background:#141a23;color:#e8eef7;padding:0 8px;" />'
    +'<input id="wj-q" placeholder="必应搜索…" style="width:150px;height:28px;border:1px solid #3a4656;border-radius:4px;background:#141a23;color:#e8eef7;padding:0 8px;" />';
  for(var k in {'button':'height:28px;border:1px solid #3a4656;border-radius:4px;background:#2a3646;color:#dfe8f4;cursor:pointer;padding:0 8px;'}){}
  bar.querySelectorAll('button').forEach(function(b){b.style.cssText+='height:28px;border:1px solid #3a4656;border-radius:4px;background:#2a3646;color:#dfe8f4;cursor:pointer;padding:0 6px;';});
  document.body.appendChild(bar);
  document.body.style.marginTop='44px';
  function nav(v){v=(v||'').trim();if(!v)return;window.pywebview.api.nav(v);}
  document.getElementById('wj-back').onclick=function(){history.back();};
  document.getElementById('wj-fwd').onclick=function(){history.forward();};
  document.getElementById('wj-re').onclick=function(){location.reload();};
  document.getElementById('wj-home').onclick=function(){nav('%s');};
  document.getElementById('wj-addr').onkeydown=function(e){if(e.key==='Enter')nav(this.value);};
  document.getElementById('wj-q').onkeydown=function(e){if(e.key==='Enter')nav('%s/search?q='+encodeURIComponent(this.value));};
  syncAddr();
})();
""" % (BING_HOME, BING_HOME)


class BrowserApi:
    def __init__(self):
        self.win = None

    def nav(self, value):
        value = (value or "").strip()
        if not value:
            return
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value) and "." not in value.split("/")[0]:
            value = BING_HOME + "/search?q=" + quote(value)
        else:
            value = normalize_url(value)
        self.win.load_url(value)


def open_builtin(url=None):
    api = BrowserApi()
    win = webview.create_window("内置浏览器 · 必应引擎", url or BING_HOME,
                                width=1100, height=760, js_api=api)
    api.win = win

    def inject():
        try:
            win.evaluate_js(TOOLBAR_JS)
        except Exception:
            pass
    win.events.loaded += inject
    return win

# ---------------------------------------------------------------- 主窗口 API
class Api:
    def get_state(self):
        return {
            "sites": DATA["sites"],
            "config": DATA["config"],
            "autostart": get_autostart(),
            "browsers": {k: bool(v) for k, v in BROWSERS.items()},
            "open_label": OPEN_LABEL,
        }

    def add_batch(self, rows):
        """批量添加：每行 {line:'名字|URL'(也认 + - 分隔), tag:'标签'}，
        每行按各自设置的标签归类，输入新标签名即新建标签。"""
        added, failed = 0, []
        for i, r in enumerate(rows or [], 1):
            line = (r.get("line") or "").strip()
            tag = (r.get("tag") or "").strip() or "未分类"
            if not line:
                continue
            m = re.match(r"^(?P<name>.+?)(?P<sep>[|+\-])"
                         r"(?P<url>(?:https?://)?[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+(?::\d+)?(?:/\S*)?)\s*$",
                         line)
            if not m or not m.group("name").strip():
                failed.append("第%d行: %s" % (i, line))
                continue
            nid = max([s["id"] for s in DATA["sites"]], default=0) + 1
            DATA["sites"].append({"id": nid, "name": m.group("name").strip(),
                                  "url": normalize_url(m.group("url").strip()),
                                  "tag": tag, "open": "global", "count": 0})
            added += 1
        save_data()
        return {"added": added, "failed": failed, "sites": DATA["sites"]}

    def poll(self):
        return {"rev": DATA_REV}

    def reload_sites(self):
        try:
            with open(SITES_FILE, "r", encoding="utf-8-sig") as f:
                DATA["sites"] = _parse_sites_txt(f.read())
        except Exception:
            return {"ok": False}
        return {"ok": True, "sites": DATA["sites"]}

    def add_site(self, item):
        nid = max([s["id"] for s in DATA["sites"]], default=0) + 1
        site = {"id": nid, "name": (item.get("name") or "").strip() or "未命名",
                "url": normalize_url(item.get("url")), "tag": (item.get("tag") or "").strip() or "未分类",
                "open": item.get("open", "global"), "count": 0}
        DATA["sites"].append(site)
        save_data()
        return site

    @staticmethod
    def _split_batch_line(line):
        """支持 名字|URL / 名字+URL / 名字-URL，取三个分隔符中最先出现者切分。"""
        idxs = [(line.find(c), c) for c in "|+-" if line.find(c) > 0]
        if not idxs:
            return None
        pos, sep = min(idxs)
        name, url = line[:pos].strip(), line[pos + 1:].strip()
        if not name or not url:
            return None
        return {"name": name, "url": url}

    def add_batch(self, rows):
        added, failed, nid = 0, [], max([s["id"] for s in DATA["sites"]], default=0)
        for row in rows or []:
            parsed = self._split_batch_line((row.get("line") or "").strip())
            if not parsed:
                failed.append(row.get("line") or "")
                continue
            nid += 1
            DATA["sites"].append({"id": nid, "name": parsed["name"],
                                  "url": normalize_url(parsed["url"]),
                                  "tag": (row.get("tag") or "").strip() or "未分类",
                                  "open": "global", "count": 0})
            added += 1
        save_data()
        return {"added": added, "failed": failed, "sites": DATA["sites"]}

    def update_site(self, item):
        for s in DATA["sites"]:
            if s["id"] == int(item["id"]):
                s.update({"name": (item.get("name") or "").strip() or s["name"],
                          "url": normalize_url(item.get("url")) or s["url"],
                          "tag": (item.get("tag") or "").strip() or "未分类",
                          "open": item.get("open", s["open"])})
                save_data()
                return s
        return None

    def delete_site(self, sid):
        DATA["sites"] = [s for s in DATA["sites"] if s["id"] != int(sid)]
        save_data()
        return True

    def open_site(self, sid):
        for s in DATA["sites"]:
            if s["id"] == int(sid):
                method = resolve_open_method(s)
                open_url_with(method, s["url"])
                s["count"] = int(s.get("count", 0)) + 1
                save_data()
                return {"count": s["count"]}
        return None

    def ping_all(self):
        results = {}
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(ping_host, s["url"]): s["id"] for s in DATA["sites"]}
            for fut in futs:
                results[str(futs[fut])] = fut.result()
        return results

    def save_config(self, cfg):
        DATA["config"] = cfg
        save_data()
        return True

    def set_autostart(self, enabled):
        return set_autostart(bool(enabled))

    def export_list(self, fmt):
        win = webview.windows[0]
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        name = "网站列表.csv" if fmt == "csv" else "网站列表.json"
        path = win.create_file_dialog(webview.SAVE_DIALOG, directory=desktop,
                                      save_filename=name,
                                      file_types=("CSV (*.csv)",) if fmt == "csv" else ("JSON (*.json)",))
        if not path:
            return None
        path = path if isinstance(path, str) else path[0]
        if fmt == "csv":
            import csv
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["网站名称", "网站URL", "标签", "跳转次数", "打开方式"])
                for s in DATA["sites"]:
                    w.writerow([s["name"], s["url"], s["tag"], s.get("count", 0),
                                OPEN_LABEL.get(s.get("open", "global"), s.get("open"))])
        else:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(DATA["sites"], f, ensure_ascii=False, indent=2)
        return path

    def builtin_search(self, q):
        open_builtin(BING_HOME + "/search?q=" + quote((q or "").strip()))
        return True

# ---------------------------------------------------------------- 前端页面
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>网站快速跳转</title>
<style>
:root{--bg:#f5f6fa;--side-bg:#cfe3f7;--side-fg:#23415e;--head-bg:#f2d0cb;--head-fg:#8a3324;
--name-bg:#b8dcec;--name-fg:#123c55;--url-bg:#9fd3e8;--url-fg:#0d3b52;--tag-bg:#c9ccd4;--tag-fg:#2f3237;
--count-bg:#6f5b9e;--count-fg:#fff;--open-bg:#6d8f62;--open-fg:#fff;--accent:#3f7fbf;}
*{box-sizing:border-box;margin:0;padding:0;font-family:"Microsoft YaHei","Segoe UI",sans-serif;}
html,body{height:100%;}
body{display:flex;background:var(--bg);color:#222;overflow:hidden;}
#nav{width:92px;background:var(--side-bg);color:var(--side-fg);display:flex;flex-direction:column;padding:8px 6px;gap:6px;flex:none;}
#nav button{background:transparent;border:1px solid rgba(0,0,0,.15);color:var(--side-fg);padding:10px 0;font-size:14px;cursor:pointer;border-radius:3px;}
#nav button.active{background:var(--accent);color:#fff;border-color:var(--accent);}
#nav .filler{flex:1;background:#f7ecc8;border:1px solid rgba(0,0,0,.2);border-radius:3px;}
#main{flex:1;padding:12px;overflow:auto;}
.page{display:none;height:100%;}
.page.show{display:flex;flex-direction:column;}
table{width:100%;border-collapse:collapse;border:2px solid #333;table-layout:fixed;}
th,td{border:1px solid #444;padding:7px 6px;font-size:13px;text-align:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
th{background:var(--head-bg);color:var(--head-fg);}
td.c-name{background:var(--name-bg);color:var(--name-fg);}
td.c-url{background:var(--url-bg);color:var(--url-fg);cursor:pointer;text-decoration:underline;}
td.c-tag{background:var(--tag-bg);color:var(--tag-fg);}
td.c-count{background:var(--count-bg);color:var(--count-fg);}
td.c-open{background:var(--open-bg);color:var(--open-fg);}
td.lat-ok{background:#c9ecc4;color:#1c6b12;}
td.lat-mid{background:#ffe9a8;color:#8a6400;}
td.lat-bad{background:#f5b1b1;color:#8f1414;}
td.lat-na{background:#ddd;color:#666;}
.toolbar{display:flex;gap:8px;margin-bottom:10px;align-items:center;}
.toolbar input[type=text]{flex:1;height:30px;border:1px solid #999;border-radius:3px;padding:0 8px;}
.btn{background:var(--accent);color:#fff;border:none;border-radius:3px;padding:7px 14px;cursor:pointer;font-size:13px;}
.btn.gray{background:#777;}
.btn.danger{background:#b3403a;}
.card{background:rgba(255,255,255,.55);border:1px solid #bbb;border-radius:6px;padding:14px;margin-bottom:12px;}
.card h3{font-size:14px;margin-bottom:10px;border-left:4px solid var(--accent);padding-left:8px;}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px 14px;}
.grid label{display:flex;align-items:center;gap:6px;font-size:12px;}
.grid input[type=color]{width:44px;height:26px;border:1px solid #999;padding:1px;background:#fff;}
.rowline{display:flex;gap:12px;align-items:center;margin:6px 0;font-size:13px;flex-wrap:wrap;}
select,input[type=text].fi{height:30px;border:1px solid #999;border-radius:3px;padding:0 6px;font-size:13px;}
.form label{display:block;margin:8px 0 4px;font-size:13px;}
.form input[type=text]{width:420px;max-width:90%;}
.tags{display:flex;flex-wrap:wrap;gap:10px;}
.tagcard{min-width:120px;padding:12px 16px;border-radius:6px;background:var(--name-bg);color:var(--name-fg);cursor:pointer;text-align:center;border:1px solid rgba(0,0,0,.2);}
.tagcard b{display:block;font-size:15px;}
#ctx{position:fixed;display:none;background:#fff;border:1px solid #888;border-radius:4px;box-shadow:2px 3px 8px rgba(0,0,0,.3);z-index:99;}
#ctx div{padding:6px 18px;font-size:13px;cursor:pointer;}
#ctx div:hover{background:var(--accent);color:#fff;}
</style>
</head>
<body>
<div id="nav">
  <button data-p="list" class="active">列表</button>
  <button data-p="settings">设置</button>
  <button data-p="add">添加</button>
  <button data-p="tags">分类</button>
  <div class="filler"></div>
</div>
<div id="main">
  <div class="page show" id="page-list">
    <div class="toolbar">
      <input type="text" id="kw" placeholder="搜索名称 / URL / 标签…">
      <input type="text" id="bingq" placeholder="必应搜索（内置浏览器打开）" style="max-width:220px">
      <button class="btn" id="bingbtn">搜索</button>
      <button class="btn gray" id="reping">重新测试</button>
      <button class="btn gray" id="reloadtxt" title="从程序同目录的 网站列表.txt 重新载入">重新读取</button>
      <span id="tagfilter" style="font-size:12px;color:#555"></span>
    </div>
    <table>
      <colgroup><col style="width:13%"><col style="width:37%"><col style="width:11%"><col style="width:12%"><col style="width:11%"><col style="width:16%"></colgroup>
      <thead><tr><th>网站名称</th><th>网站URL(点击跳转)</th><th>延迟</th><th>标签</th><th>跳转次数</th><th>打开方式</th></tr></thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>

  <div class="page" id="page-settings">
    <div class="card">
      <h3>外观主题</h3>
      <div class="rowline">预设主题：
        <select id="preset">
          <option value="light">浅色（如图）</option><option value="dark">深色</option>
          <option value="green">护眼绿</option><option value="blue">科技蓝</option>
        </select>
        <span style="color:#777;font-size:12px">（选预设后可再逐项微调，点“保存设置”生效并记忆）</span>
      </div>
      <div class="grid" id="colors"></div>
    </div>
    <div class="card">
      <h3>打开方式</h3>
      <div class="rowline">默认打开方式：
        <select id="defopen"></select>
        <span style="color:#777;font-size:12px">内置浏览器使用必应引擎，防止系统没有/浏览器太低级</span>
      </div>
    </div>
    <div class="card">
      <h3>系统</h3>
      <div class="rowline">
        <label><input type="checkbox" id="autostart"> 开机自启动</label>
        <button class="btn" id="expcsv">导出网站列表(CSV)</button>
        <button class="btn" id="expjson">导出网站列表(JSON)</button>
      </div>
    </div>
    <div class="rowline"><button class="btn" id="savecfg">保存设置</button></div>
  </div>

  <div class="page" id="page-add">
    <div class="card form" style="max-width:560px">
      <h3 id="addtitle">添加网站</h3>
      <label>网站名称</label><input type="text" id="f-name" class="fi">
      <label>网站URL</label><input type="text" id="f-url" class="fi" placeholder="如 https://example.com">
      <label>自定义标签（类型）</label><input type="text" id="f-tag" class="fi" list="taglist"><datalist id="taglist"></datalist>
      <label>打开方式</label><select id="f-open"></select>
      <div class="rowline" style="margin-top:14px">
        <button class="btn" id="f-save">添加</button>
        <button class="btn gray" id="f-cancel" style="display:none">取消编辑</button>
      </div>
    </div>
    <div class="card form">
      <h3>批量添加（一行一个：名字|URL、名字+URL、名字-URL 三种写法都认）</h3>
      <textarea id="b-text" rows="5" style="width:100%;border:1px solid #999;border-radius:3px;padding:6px;font-size:13px"
        placeholder="沙箱|https://s.threatbook.com 工具&#10;百度+baidu.com&#10;必应-bing.com"></textarea>
      <div class="rowline"><button class="btn gray" id="b-parse">解析行并设置标签</button>
        <span style="color:#777;font-size:12px">解析后每行可下拉选已有标签，或输入新标签名（自动新建），各行独立归类</span></div>
      <div id="b-rows"></div>
      <div class="rowline"><button class="btn" id="b-save">批量添加</button></div>
      <datalist id="b-tags"></datalist>
    </div>
  </div>

  <div class="page" id="page-tags">
    <div class="card"><h3>分类（点击标签筛选列表）</h3><div class="tags" id="tagwrap"></div></div>
  </div>
</div>
<div id="ctx"><div data-a="open">打开网站</div><div data-a="edit">编辑</div><div data-a="del">删除</div></div>
<script>
window.addEventListener('error',e=>{window.__err=String(e.message||e.error||'');});
const PRESETS = {
 light:{bg:'#f5f6fa',side_bg:'#cfe3f7',side_fg:'#23415e',head_bg:'#f2d0cb',head_fg:'#8a3324',name_bg:'#b8dcec',name_fg:'#123c55',url_bg:'#9fd3e8',url_fg:'#0d3b52',tag_bg:'#c9ccd4',tag_fg:'#2f3237',count_bg:'#6f5b9e',count_fg:'#ffffff',open_bg:'#6d8f62',open_fg:'#ffffff',accent:'#3f7fbf'},
 dark:{bg:'#17181d',side_bg:'#23252e',side_fg:'#d8dce8',head_bg:'#2e3140',head_fg:'#e6e9f5',name_bg:'#243447',name_fg:'#cfe3ff',url_bg:'#1f3a4d',url_fg:'#c9ecff',tag_bg:'#33363f',tag_fg:'#dfe2ea',count_bg:'#4a3f75',count_fg:'#e8e2ff',open_bg:'#3d5a40',open_fg:'#dff0df',accent:'#5b8dd9'},
 green:{bg:'#eaf3e6',side_bg:'#d7ead0',side_fg:'#2f4a2a',head_bg:'#cfe4c6',head_fg:'#33502c',name_bg:'#dcefd4',name_fg:'#2f4a2a',url_bg:'#cfe6c6',url_fg:'#274422',tag_bg:'#e2e8dc',tag_fg:'#3c4438',count_bg:'#7d9b6f',count_fg:'#ffffff',open_bg:'#5f8a54',open_fg:'#ffffff',accent:'#588a4c'},
 blue:{bg:'#0e1a2b',side_bg:'#12283f',side_fg:'#cfe4ff',head_bg:'#16334f',head_fg:'#bcd9ff',name_bg:'#14395c',name_fg:'#cfe8ff',url_bg:'#10416b',url_fg:'#d2ecff',tag_bg:'#1c2c40',tag_fg:'#c8d6ea',count_bg:'#274b8f',count_fg:'#eaf2ff',open_bg:'#1f5c46',open_fg:'#d9f2e4',accent:'#2f8fd9'}
};
const COLOR_LABEL = {bg:'页面背景',side_bg:'侧栏背景',side_fg:'侧栏字体',head_bg:'表头背景',head_fg:'表头字体',
 name_bg:'名称块背景',name_fg:'名称块字体',url_bg:'URL块背景',url_fg:'URL块字体',tag_bg:'标签块背景',tag_fg:'标签块字体',
 count_bg:'次数块背景',count_fg:'次数块字体',open_bg:'打开方式块背景',open_fg:'打开方式块字体',accent:'主题强调色'};
let S=null, lat={}, filterTag=null, editId=null, ctxId=null;
const $=id=>document.getElementById(id);
function applyTheme(t){for(const k in COLOR_LABEL){document.documentElement.style.setProperty('--'+k.replace('_','-'),t[k]);}
 // CSS 变量名用中划线
 const map={bg:'--bg',side_bg:'--side-bg',side_fg:'--side-fg',head_bg:'--head-bg',head_fg:'--head-fg',name_bg:'--name-bg',name_fg:'--name-fg',url_bg:'--url-bg',url_fg:'--url-fg',tag_bg:'--tag-bg',tag_fg:'--tag-fg',count_bg:'--count-bg',count_fg:'--count-fg',open_bg:'--open-bg',open_fg:'--open-fg',accent:'--accent'};
 for(const k in map){if(t[k])document.documentElement.style.setProperty(map[k],t[k]);}}
function openLabel(s){return S.open_label[s.open]||s.open;}
function latCell(r){
 if(r===undefined)return '<td class="lat-na">…</td>';
 if(r===null)return '<td class="lat-bad">超时</td>';
 const ms=r.ms,tip='测试方法：'+r.m;
 if(ms>=2000)return '<td class="lat-bad" title="'+tip+'">'+ms+'ms</td>';
 if(ms>300)return '<td class="lat-mid" title="'+tip+'">'+ms+'ms</td>';
 return '<td class="lat-ok" title="'+tip+'">'+ms+'ms</td>';}
function renderList(){
 const kw=$('kw').value.trim().toLowerCase();
 const rows=S.sites.filter(s=>(!filterTag||s.tag===filterTag)&&(!kw||(s.name+s.url+s.tag).toLowerCase().includes(kw)));
 $('tagfilter').textContent=filterTag?('分类筛选：'+filterTag+'  (点击清除)'):'';
 $('tbody').innerHTML=rows.map(s=>'<tr data-id="'+s.id+'">'
   +'<td class="c-name" title="'+s.name+'">'+s.name+'</td>'
   +'<td class="c-url" title="'+s.url+'">'+s.url+'</td>'
   +latCell(lat[s.id])
   +'<td class="c-tag">'+s.tag+'</td>'
   +'<td class="c-count">'+(s.count||0)+'</td>'
   +'<td class="c-open">'+openLabel(s)+'</td></tr>').join('')||'<tr><td colspan="6" style="background:#eee;color:#888">暂无网站，去“添加”页加一个吧</td></tr>';}
async function pingAll(){
 S.sites.forEach(s=>{lat[s.id]=undefined;});renderList();
 const r=await window.pywebview.api.ping_all();lat=r;renderList();}
function fillOpenSelect(sel,withGlobal){
 let h='';if(withGlobal)h+='<option value="global">跟随全局设置</option>';
 h+='<option value="system">系统默认浏览器</option><option value="builtin">内置浏览器(必应)</option>';
 if(S.browsers.edge)h+='<option value="edge">Edge浏览器</option>';
 if(S.browsers.chrome)h+='<option value="chrome">Chrome浏览器</option>';
 if(S.browsers.firefox)h+='<option value="firefox">Firefox浏览器</option>';
 sel.innerHTML=h;}
function renderColors(){
 const t=S.config.theme;
 $('colors').innerHTML=Object.keys(COLOR_LABEL).map(k=>'<label>'+COLOR_LABEL[k]+'<input type="color" data-k="'+k+'" value="'+(t[k]||'#888888')+'"></label>').join('');
 $('colors').querySelectorAll('input').forEach(i=>i.onchange=()=>{S.config.theme[i.dataset.k]=i.value;applyTheme(S.config.theme);});}
function esc(t){return String(t||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function renderTags(){
 const m={};S.sites.forEach(s=>{m[s.tag]=(m[s.tag]||0)+1;});
 $('tagwrap').innerHTML='<div class="tagcard" data-t=""><b>全部</b>'+S.sites.length+'</div>'
  +Object.keys(m).map(t=>'<div class="tagcard" data-t="'+esc(t)+'"><b>'+esc(t)+'</b>'+m[t]+'</div>').join('');
 $('tagwrap').querySelectorAll('.tagcard').forEach(c=>c.onclick=()=>{filterTag=c.dataset.t||null;show('list');renderList();});
 const opts=Object.keys(m).map(t=>'<option value="'+esc(t)+'">').join('');
 $('taglist').innerHTML=opts;$('b-tags').innerHTML=opts;}
function show(p){
 document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.p===p));
 document.querySelectorAll('.page').forEach(x=>x.classList.remove('show'));
 $('page-'+p).classList.add('show');
 if(p==='list')renderList();
 if(p==='tags')renderTags();}
async function init(){
 S=await window.pywebview.api.get_state();
 applyTheme(S.config.theme);
 fillOpenSelect($('defopen'),false);$('defopen').value=S.config.default_open||'system';
 fillOpenSelect($('f-open'),true);
 $('autostart').checked=S.autostart;
 renderColors();show('list');pingAll();
 (async function poller(){let last=null;for(;;){try{const r=await window.pywebview.api.poll();if(last!==null&&r.rev!==last){await refresh();pingAll();}last=r.rev;}catch(e){}await new Promise(rs=>setTimeout(rs,3000));}})();
 document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>{if(b.dataset.p==='add'){editId=null;resetForm();}show(b.dataset.p);});
 $('kw').oninput=renderList;
 $('tagfilter').onclick=()=>{filterTag=null;renderList();};
 $('reping').onclick=pingAll;
 $('reloadtxt').onclick=async()=>{const r=await window.pywebview.api.reload_sites();if(r&&r.ok){S.sites=r.sites;lat={};renderList();renderTags();}};
 $('bingbtn').onclick=()=>window.pywebview.api.builtin_search($('bingq').value);
 $('bingq').onkeydown=e=>{if(e.key==='Enter')window.pywebview.api.builtin_search($('bingq').value);};
 $('tbody').onclick=e=>{const tr=e.target.closest('tr');if(!tr||!tr.dataset.id)return;
   if(e.target.classList.contains('c-url')||e.target.classList.contains('c-name'))openSite(tr.dataset.id);};
 $('tbody').oncontextmenu=e=>{const tr=e.target.closest('tr');if(!tr||!tr.dataset.id)return;e.preventDefault();
   ctxId=tr.dataset.id;const c=$('ctx');c.style.display='block';c.style.left=e.clientX+'px';c.style.top=e.clientY+'px';};
 document.onclick=()=>$('ctx').style.display='none';
 $('ctx').querySelectorAll('div').forEach(d=>d.onclick=()=>{
   if(d.dataset.a==='open')openSite(ctxId);
   if(d.dataset.a==='del'){if(confirm('删除该网站？'))window.pywebview.api.delete_site(ctxId).then(refresh);}
   if(d.dataset.a==='edit'){const s=S.sites.find(x=>x.id==ctxId);if(s)startEdit(s);}});
 $('preset').onchange=()=>{S.config.theme=Object.assign({},PRESETS[$('preset').value]);applyTheme(S.config.theme);renderColors();};
 $('autostart').onchange=()=>window.pywebview.api.set_autostart($('autostart').checked);
 $('expcsv').onclick=()=>window.pywebview.api.export_list('csv');
 $('expjson').onclick=()=>window.pywebview.api.export_list('json');
 $('savecfg').onclick=async()=>{S.config.default_open=$('defopen').value;
   await window.pywebview.api.save_config(S.config);alert('设置已保存');};
 $('f-save').onclick=async()=>{
   const item={name:$('f-name').value,url:$('f-url').value,tag:$('f-tag').value,open:$('f-open').value};
   if(!item.url){alert('请填写网站URL');return;}
   if(editId){item.id=editId;await window.pywebview.api.update_site(item);}else{await window.pywebview.api.add_site(item);}
   resetForm();await refresh();show('list');};
 $('f-cancel').onclick=()=>{resetForm();};
 // 批量添加
 $('b-parse').onclick=()=>{
   const lines=$('b-text').value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
   $('b-rows').innerHTML=lines.map((ln,i)=>'<div class="rowline" style="margin:4px 0">'
     +'<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'+esc(ln)+'">'+esc(ln)+'</span>'
     +'<input class="fi" list="b-tags" data-i="'+i+'" placeholder="选/输入标签" style="width:150px"></div>').join('')
     ||'<span style="color:#888;font-size:12px">未解析到有效行</span>';};
 $('b-save').onclick=async()=>{
   const lines=$('b-text').value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
   if(!lines.length){alert('请先填写要添加的内容');return;}
   if($('b-rows').querySelectorAll('input').length!==lines.length)$('b-parse').click();
   const inputs=$('b-rows').querySelectorAll('input');
   const rows=lines.map((ln,i)=>({line:ln,tag:(inputs[i]&&inputs[i].value)||''}));
   const r=await window.pywebview.api.add_batch(rows);
   S.sites=r.sites;lat={};renderList();renderTags();
   $('b-text').value='';$('b-rows').innerHTML='';
   alert('成功添加 '+r.added+' 个网站'+(r.failed.length?('\n以下行格式无法识别，未添加：\n'+r.failed.join('\n')):''));};}
async function openSite(id){const r=await window.pywebview.api.open_site(id);if(r){const s=S.sites.find(x=>x.id==id);if(s)s.count=r.count;renderList();}}
async function refresh(){S=await window.pywebview.api.get_state();renderList();renderTags();}
function resetForm(){editId=null;$('addtitle').textContent='添加网站';$('f-save').textContent='添加';$('f-cancel').style.display='none';
 $('f-name').value='';$('f-url').value='';$('f-tag').value='';$('f-open').value='global';}
function startEdit(s){editId=s.id;show('add');$('addtitle').textContent='编辑网站';$('f-save').textContent='保存修改';$('f-cancel').style.display='';
 $('f-name').value=s.name;$('f-url').value=s.url;$('f-tag').value=s.tag;$('f-open').value=s.open;}
let inited=false;
function boot(){if(inited)return;inited=true;window.__boot=1;init().then(()=>{window.__boot=2;}).catch(e=>{window.__err='init:'+e;});}
function waitApi(n){
 if(window.pywebview&&window.pywebview.api&&Object.keys(window.pywebview.api).length){boot();return;}
 if(n<300)setTimeout(()=>waitApi(n+1),50);
}
window.addEventListener('pywebviewready',boot);
waitApi(0);
</script>
</body>
</html>"""

# ---------------------------------------------------------------- 启动
def main():
    start_local_server()
    api = Api()
    win = webview.create_window("网站快速跳转 WebJump", html=HTML, width=1000, height=640,
                                js_api=api, min_size=(860, 560))
    auto = os.environ.get("WEBJUMP_AUTOCLOSE")
    if auto:
        def close():
            time.sleep(4)
            try:
                info = win.evaluate_js(
                    "JSON.stringify({pw:typeof window.pywebview,api:(window.pywebview&&window.pywebview.api)?Object.keys(window.pywebview.api).length:-1,boot:window.__boot||0,err:window.__err||null,rows:document.querySelectorAll('#tbody tr').length,state:!!S,nav:document.querySelectorAll('#nav button').length})")
            except Exception as e:
                info = "DIAG-FAIL " + str(e)
            try:
                print("DIAG", info)
            except Exception:
                pass
            try:
                with open(os.path.join(BASE_DIR, "webjump_diag.txt"), "w", encoding="utf-8") as f:
                    f.write(str(info))
            except Exception:
                pass
            time.sleep(max(0.0, float(auto) - 4))
            win.destroy()
        threading.Thread(target=close, daemon=True).start()
    webview.start(gui="edgechromium", debug=bool(os.environ.get("WEBJUMP_DEBUG")))


if __name__ == "__main__":
    main()
