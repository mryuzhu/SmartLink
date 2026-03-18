# SmartLink

SmartLink 是一个面向 Windows 主机的局域网控制工具，保留了原项目的 ADB、MQTT、串口读卡和托盘能力，并补齐了更可维护的 Flask 控制台、iPhone 快捷指令 HTTP API、安全鉴权、日志、配置导入导出和移动端按钮页。

## 主要能力

- 启动项管理：支持搜索、分类筛选、新建、编辑、删除、一键执行、批量删除、批量导出。
- iOS 局域网控制：内置 `/api/health`、`/api/actions`、`/api/run`、`/api/system/*` 接口，支持快捷指令和 Webhook。
- 安全增强：Token 鉴权、局域网网段 / IP 白名单、动作白名单、统一 JSON 响应、日志脱敏。
- 稳定性增强：配置迁移、滚动日志、最近请求记录、最近使用动作、后台执行队列。
- 兼容原能力：ADB 设备连接、巴法云 MQTT 触发、串口读卡触发、Windows 托盘、开机自启。
- 移动体验：`/mobile` 页面可直接在 iPhone Safari 收藏后点击控制。

## 目录结构

```text
E:\my codex
├─ SmartLink.py
├─ smartlink
│  ├─ routes
│  ├─ services
│  ├─ static
│  └─ templates
├─ config
├─ logs
└─ tests
```

## 运行环境

- Python 3.11+
- Windows 主机优先
- 已安装 `adb` 并加入 PATH（如果需要 Android 控制）

## 安装

```powershell
pip install -e .[dev]
```

## 启动

```powershell
python SmartLink.py
```

常用启动参数：

```powershell
python SmartLink.py --no-browser
python SmartLink.py --disable-tray
python SmartLink.py --config E:\my codex\config\launcher_config.json
```

启动后默认访问：

- 控制台：[http://127.0.0.1:5000/](http://127.0.0.1:5000/)
- 手机按钮页：[http://127.0.0.1:5000/mobile](http://127.0.0.1:5000/mobile)

## 测试与检查

```powershell
ruff check .
pytest
```

## iPhone 接入

完整步骤见 [SHORTCUTS_GUIDE.md](SHORTCUTS_GUIDE.md)。

快捷说明：

1. 打开控制台，进入 “iOS 快捷指令接口说明”。
2. 复制 `API Base` 和 `X-SmartLink-Token`。
3. 在 iPhone 快捷指令里使用“获取 URL 内容”。
4. 方法选择 `POST`，Header 填入 `X-SmartLink-Token`。
5. URL 使用 `http://你的局域网IP:端口/api/run/动作名` 或系统接口。

## 配置文件

默认配置文件：

```text
E:\my codex\config\launcher_config.json
```

支持从旧版 `%USERPROFILE%\launcher_config.json` 自动迁移。

你也可以通过环境变量覆盖：

- `SMARTLINK_CONFIG_FILE`
- `SMARTLINK_HOST`
- `SMARTLINK_PORT`
- `SMARTLINK_API_TOKEN`

## 音量接口说明

`POST /api/system/volume` 已实现接口和参数校验。

- 如果系统安装了 `nircmd.exe`，会直接调用设置系统音量。
- 如果未安装，接口会返回 `volume_not_supported`，不会影响其他功能。

## SSH 说明

HTTP API 是主路径，SSH 只是可选增强。

- 你可以在控制台填写 SSH 主机、用户和端口。
- 控制台会自动生成一条 iOS 快捷指令可参考的 SSH 命令模板。
- 即使不配置 SSH，iPhone 快捷指令链路也可以完整工作。
