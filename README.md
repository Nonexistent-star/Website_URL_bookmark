# WebJump 网站快速跳转

![icon](web-kz/icon128.png)

一款轻量级的 Windows 桌面网站导航 / 收藏管理工具：把常用网站集中在一张表里，一键跳转、实时测延迟、按标签分类，还能用 Edge 浏览器扩展在浏览网页时一键收藏进列表。内置必应引擎浏览器，哪怕目标机器没有像样的浏览器也能用。

---

## 功能亮点

| 模块 | 说明 |
| --- | --- |
| 网站列表 | 名称 / URL / 延迟 / 标签 / 跳转次数 / 打开方式 六列总览，点名称或 URL 即跳转并累计次数，右键可打开、编辑、删除 |
| 延迟监测 | 三种测试方法自动兜底：ICMP ping → TCP 端口握手(443/80) → HTTP 请求。哪个先通用哪个，全不通才报超时；绿 ≤300ms、黄 >300ms、红 ≥2000ms 或超时 |
| 标签分类 | 自定义标签（类型），分类页聚合计数、点击筛选；支持批量添加时逐行独立归类 |
| 批量添加 | 一行一个，`名字|URL`、`名字+URL`、`名字-URL` 三种写法都认；解析后每行下拉选已有标签或输入新标签（自动新建） |
| 主题自定义 | 浅色 / 深色 / 护眼绿 / 科技蓝四套预设，另可逐项自定义 15 处块颜色与字体颜色并记忆 |
| 打开方式 | 系统默认浏览器 / 内置浏览器 / Edge / Chrome / Firefox 可选，支持全局默认与单站覆盖 |
| 内置浏览器 | 基于系统 Edge WebView2（Chromium 内核），首页为必应，注入地址栏工具条（前进/后退/刷新/必应搜索），不依赖第三方浏览器 |
| 浏览器扩展 | 附带 Edge 扩展 `web-kz`：浏览任意网页时点工具栏图标，自动获取当前页标题与地址，填标签和打开方式后一键收藏进主程序 |
| 数据外置 | 网站列表存为 `网站列表.txt`（每行一条，记事本可直接编辑），程序与数据分离，拷走文件夹即完成迁移 |
| 安装部署 | 提供 Inno Setup 安装包：自选安装位置、中文向导、自动检测并静默补装 WebView2 运行时，别人拿到安装即用 |

## 界面结构

主窗口 1000×640，左侧四个导航页：

- **列表**：核心表格 + 搜索框 + 必应搜索入口 + 重新测试 / 重新读取按钮
- **设置**：主题预设与逐块配色、默认打开方式、开机自启动、导出 CSV / JSON
- **添加**：单个添加与批量添加
- **分类**：按标签聚合，点击筛选列表

## 快速开始

### 方式一：安装程序（推荐分发）

运行 `installer_out/WebJump-Setup-1.0.0.exe`：

1. 中文向导，可自选安装位置；默认按当前用户安装（无需管理员权限），右键"以管理员身份运行"则安装为全机；
2. 安装过程自动检测 WebView2 运行时：已装跳过，未装则静默补装内嵌的微软官方组件；
3. 自动创建开始菜单项，可选创建桌面快捷方式；
4. 卸载会移除程序文件，但保留你的 `网站列表.txt` 等用户数据。

### 方式二：单文件 exe

`dist/WebJump.exe` 为 PyInstaller 单文件产物，内嵌完整 Python 运行时与依赖，拷到任意 Windows 机器双击即用（程序、`网站列表.txt`、`webjump_data.json` 放在同一目录即可整体迁移）。

### 方式三：源码运行

```bash
pip install pywebview
python webjump.py
```

要求 Windows 10/11，系统带有 Edge WebView2 运行时（Win10/11 绝大多数机器已自带）。

## 数据文件说明

程序目录下两个数据文件：

- `网站列表.txt`：网站列表本体。每行一个网站，格式 `名称 | URL | 标签 | 打开方式 | 跳转次数`，`#` 开头为注释。可用记事本批量增删行，程序内点"重新读取"或重启生效；程序内的添加、删除、计数也会自动写回。首次运行自动生成空白模板。
- `webjump_data.json`：仅存主题配色等设置。

打开方式字段可选：`global`(跟随全局) / `system`(系统默认浏览器) / `builtin`(内置浏览器) / `edge` / `chrome` / `firefox`。

## 浏览器扩展 web-kz

位于 `web-kz/` 目录的 Edge MV3 扩展，与主程序通过本地回环 `127.0.0.1:47811` 通信，不向任何外部服务器发送数据。

安装（Edge）：

1. 地址栏打开 `edge://extensions/`；
2. 开启"开发人员模式"；
3. 点"加载解压缩的扩展"，选择 `web-kz` 文件夹；
4. 固定工具栏闪电图标。

使用：浏览任意网页时点击图标，名称与网址自动填好，标签可下拉选已有或输入新标签，选择打开方式后点"添加到 WebJump"，主程序列表约 3 秒内自动刷新。主程序未运行时会给出提示。

## 从源码构建

```bash
# 1. 打包单文件 exe（内嵌嵌入式 Python 运行时，需先准备 embed_py 目录）
python build_exe.py

# 2. 一键重建：打 exe + 编译安装包（Inno Setup 已置于 tools/innosetup）
python build_setup.py
```

构建链说明：

- `build_exe.py`：PyInstaller 单文件打包，捆绑 `embed_py`（Python 3.11 嵌入式版 + pywebview）与应用图标 `app.ico`；
- `WebJump-Setup.iss`：Inno Setup 安装脚本，中文界面、自选目录、WebView2 注册表检测 + 静默补装、安装/卸载前自动结束主程序进程；
- `gen_icon.py`：应用图标生成脚本（蓝色渐变 + 地球经纬线 + 金色闪电，寓意"全球网站、极速跳转"）。

注意：重新打包前请先关闭正在运行的 WebJump，否则 exe 被占用无法覆盖。

## 目录结构

```
web-all/
├── webjump.py            # 主程序源码（界面 / 延迟测试 / 本地监听服务 / 内置浏览器）
├── build_exe.py          # PyInstaller 打包脚本
├── build_setup.py        # 一键重建 exe + 安装包
├── WebJump-Setup.iss     # Inno Setup 安装脚本
├── gen_icon.py           # 图标生成脚本
├── app.ico               # 应用图标
├── web-kz/               # Edge 扩展（manifest / popup / 图标 / 使用说明）
├── installer_res/        # 随安装包分发的资源（空白列表模板）
├── tools/                # 构建工具链（Inno Setup、WebView2 补装包、语言包）
├── dist/                 # 打包产物 WebJump.exe
└── installer_out/        # 安装包产物 WebJump-Setup-1.0.0.exe
```

## 常见问题

**Q：首次运行 exe 弹 SmartScreen 警告？**
A：程序有做自代码签名，选择"仍要运行"即可。

**Q：内置浏览器打不开？**
A：目标机器缺少 WebView2 运行时。运行安装程序会自动补装；或从微软官网安装 Edge WebView2 Runtime。列表跳转使用系统浏览器不受影响。

**Q：为什么某个网站 ping 不通却显示绿色延迟？**
A：部分站点禁 ICMP ping。程序按 ping → TCP → HTTP 顺序兜底测试，取第一个成功的方法（延迟格悬停可见所用方法）。

**Q：想改监听端口？**
A：主程序改 `webjump.py` 中的 `KZ_PORT`（默认 47811），扩展端同步改 `web-kz/popup.js` 中的 `BASE`。

**Q：如何完全离线部署 WebView2？**
A：默认内嵌约 2MB 的联网补装包（在线安装）。完全无网环境可从微软官网下载约 170MB 的 Standalone 离线安装包，替换 `tools/MicrosoftEdgeWebview2RuntimeInstallerX64.exe` 后重编安装包即可。

## 技术栈

Python 3.11 · pywebview (EdgeChromium / WebView2) · PyInstaller · Inno Setup · Edge Extension (Manifest V3) · 原生 HTML/CSS/JS 界面

## 许可

个人学习与内部使用；如需对外分发请注明出处。
