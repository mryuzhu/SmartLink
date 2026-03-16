# iPhone 快捷指令接入指南

本文说明如何把 SmartLink 接到 iPhone 的“快捷指令”，实现一键控制局域网内的电脑。

## 前提条件

1. 电脑和 iPhone 在同一局域网。
2. SmartLink 已启动。
3. 控制台里已经拿到：
   - 局域网地址
   - 端口
   - `X-SmartLink-Token`

## 快捷指令基础配置

在 iPhone 的“快捷指令”中创建新快捷指令，添加动作“获取 URL 内容”。

推荐填写：

- URL：`http://电脑局域网IP:5000/api/...`
- 方法：`POST`
- Headers：
  - Key：`X-SmartLink-Token`
  - Value：控制台里显示的完整 Token
- 请求体：JSON

所有 API 都返回统一 JSON：

```json
{
  "success": true,
  "message": "动作已执行。",
  "data": {},
  "error": null
}
```

## 示例 1：打开某个软件

前提：先在 SmartLink 控制台里创建动作，例如：

- 名称：`打开记事本`
- 类型：`exe`
- 命令：`notepad.exe`
- 勾选：`允许 API / iPhone 调用`

快捷指令配置：

- URL：

```text
http://电脑局域网IP:5000/api/run/打开记事本
```

- 方法：`POST`
- Header：`X-SmartLink-Token`

## 示例 2：调节亮度

快捷指令配置：

- URL：

```text
http://电脑局域网IP:5000/api/system/brightness
```

- 方法：`POST`
- 请求体 JSON：

```json
{
  "value": 50
}
```

说明：

- 亮度范围是 `0` 到 `100`
- 当前内置实现优先支持 Windows

## 示例 3：关闭电脑

快捷指令配置：

- URL：

```text
http://电脑局域网IP:5000/api/system/shutdown
```

- 方法：`POST`
- Header：`X-SmartLink-Token`

你也可以调用动作白名单：

```text
http://电脑局域网IP:5000/api/run/关机
```

## 推荐的快捷指令组合方式

### 方式 A：直接动作按钮

适合常用固定操作，例如：

- 打开记事本
- 锁定电脑
- 关闭电脑

### 方式 B：先询问，再调用

适合亮度或多个动作场景：

1. 添加“从菜单中选取”
2. 选项例如：`亮度 30`、`亮度 50`、`亮度 80`
3. 根据选项调用不同 JSON 请求

### 方式 C：语音触发

把快捷指令重命名为容易说出的短句，例如：

- “打开电脑记事本”
- “电脑亮度五十”
- “关闭这台电脑”

之后可直接通过 Siri 调用。

## Safari 按钮页

如果不想先写快捷指令，也可以直接用手机打开：

```text
http://电脑局域网IP:5000/mobile
```

页面输入 Token 后即可直接点击按钮执行收藏动作、锁屏、重启、关机和亮度控制。

## SSH 备用方案

HTTP API 是主路径，SSH 是可选增强方案。

如果你的 Windows 主机已经配置 OpenSSH Server，也可以在快捷指令里使用“运行脚本（通过 SSH）”。

但推荐优先使用 HTTP API，因为：

- 配置更轻
- 不依赖系统 SSH 环境
- 更容易做白名单控制和日志记录
- 对 iPhone 快捷指令更直接
