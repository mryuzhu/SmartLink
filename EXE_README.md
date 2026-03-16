# SmartLink 软件说明

## 目录内容
- `SmartLink.exe`：Windows 可执行文件。
- `使用说明.md`：本说明文件的副本。

## 运行方式
1. 双击 `SmartLink.exe`。
2. 或在命令行中运行：

```powershell
.\SmartLink.exe
```

可选参数：

```powershell
.\SmartLink.exe --no-browser
.\SmartLink.exe --disable-tray
```

## 首次使用
1. 启动后打开 Web 控制台。
2. 在全局设置里确认监听地址、端口和 Token。
3. 如果需要让 iPhone 或局域网设备访问，请把监听地址设为 `0.0.0.0`。
4. 打开 `/mobile` 可进入手机端简化控制页。

## iPhone 快捷指令
常用接口：

- `GET /api/health`
- `GET /api/actions`
- `POST /api/run/<action_name>`
- `POST /api/system/brightness`
- `POST /api/system/shutdown`

请求头需要携带：

```text
X-SmartLink-Token: 你的Token
```

更详细的接入说明见源码包中的 `SHORTCUTS_GUIDE.md`。

## ADB 配对
在 Web 控制台的 ADB 管理区域可使用“连接设备 / 配对设备”功能，支持：

```text
adb pair <ip>:<pair_port> <pair_code>
adb connect <ip>:<debug_port>
```

未填写调试端口时，默认尝试 `5555`。

## 注意事项
- Windows 防火墙可能会拦截局域网访问，需要放行对应端口。
- 如果亮度或锁屏功能在当前机器不可用，系统会返回兼容提示。
- 日志默认保留最近 50 条供 Web 界面查看，完整滚动日志在 `logs` 目录。
