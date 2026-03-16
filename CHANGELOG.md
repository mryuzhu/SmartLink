# Changelog

## 0.2.0 - 2026-03-16

- 将原单文件 `SmartLink.py` 重构为 `smartlink/` 包结构，拆分配置、路由、服务、模板和静态资源。
- 保留原有 ADB、MQTT、串口读卡和托盘能力，并补齐工程化入口。
- 新增 iOS 局域网 HTTP API：
  - `GET /api/health`
  - `GET /api/actions`
  - `POST /api/run`
  - `POST /api/run/<action_name>`
  - `POST /api/system/volume`
  - `POST /api/system/brightness`
  - `POST /api/system/shutdown`
  - `POST /api/system/restart`
  - `POST /api/system/lock`
- 新增 Token 鉴权、白名单网段 / IP 校验、动作白名单和统一 JSON 响应。
- 重做 Web 控制台 UI，新增移动端按钮页 `/mobile`。
- 新增配置导入导出、最近请求记录、滚动日志、最近动作和后台执行历史。
- 增加 Windows 开机自启配置能力。
- 重写 README，新增 `SHORTCUTS_GUIDE.md`、`.env.example`、测试和 `pyproject.toml`。
