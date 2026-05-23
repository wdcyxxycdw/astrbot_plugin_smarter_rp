# Embedded Tavern Adapter 设计

## 背景

当前插件已经被重做为 AstrBot Tavern Bridge client：AstrBot 侧只负责拦截消息并调用 `/generate`，角色卡、聊天历史、世界书和生成由外部 Tavern Bridge / SillyTavern 侧负责。

现在的新目标是把第一版缺失的 Tavern Bridge adapter 也纳入本项目，但不回到自研 RP runtime。adapter 应由两个组件协作完成：AstrBot 插件内置本地 Bridge Server，SillyTavern 安装配套扩展，由扩展调用 SillyTavern 内部角色、聊天和生成能力。

## 目标

- AstrBot 插件内置本地 WebSocket Bridge Server。
- SillyTavern 配套扩展连接该 Bridge Server。
- 角色卡绑定在 SillyTavern 扩展里配置：`adapter/account → character`。
- AstrBot session 自动绑定 SillyTavern chat：`adapter/account + astrbot_session_id → tavern_chat_id`。
- 新 session 首次出现时自动创建对应 SillyTavern chat。
- 自动创建的 chat 使用可读名称：`[AstrBot] {platform}-{session_display_name}-{session_id短码}`。
- AstrBot 插件继续保留 `/rp on` 和 `/rp off`。
- 第一版无认证，但 Bridge Server 默认只监听 `127.0.0.1`。

## 非目标

- 不要求用户手动逐个绑定 AstrBot session 到 chat。
- 不在 AstrBot 插件内实现角色卡、世界书、记忆或 prompt builder。
- 不直接读取 SillyTavern 内部文件来模拟运行时。
- 不支持多 SillyTavern 扩展客户端同时处理生成。
- 不支持远程公网暴露或认证。
- 不支持 session 级角色切换、群内用户级角色覆盖或多角色并行。
- 不在第一版实现并发生成。

## 总体架构

```text
用户在 QQ / Discord / Telegram / 其它 AstrBot adapter 发消息
  ↓
AstrBot
  ↓
Smarter RP 插件
  ├─ 判断当前 session 是否启用
  ├─ 提取 adapter/account/session/user/message
  ├─ 创建 generate job
  ├─ 通过本地 WebSocket Bridge Server 发送给 SillyTavern 扩展
  ├─ 等待 generate_result 或 generate_error
  └─ 将 reply 或 fallback 发回原平台
  ↓ WebSocket: ws://127.0.0.1:8008/ws
SillyTavern 扩展
  ├─ 维护 adapter/account → character 绑定
  ├─ 维护 adapter/account/session → chat 自动绑定
  ├─ 首次 session 自动创建 chat
  ├─ 追加用户消息到对应 chat
  ├─ 调用 SillyTavern 内部生成能力
  └─ 返回 reply
```

AstrBot 插件不理解 SillyTavern 的角色卡、世界书、预设或上下文组装细节。SillyTavern 扩展负责所有与酒馆运行时相关的操作。

## AstrBot 插件侧职责

- 启动本地 Bridge Server。
- 管理单个 SillyTavern 扩展连接。
- 拦截普通消息。
- 尊重 `/rp on` / `/rp off` session 状态。
- 将 AstrBot 消息转换为 generate job。
- 等待扩展返回结果。
- 超时、扩展未连接或扩展报错时回复 fallback。
- 丢弃已经超时的 late result。

## SillyTavern 扩展侧职责

- 连接 AstrBot Bridge Server。
- 提供绑定 UI，用于配置：

```text
adapter + platform + account_id → character_id
```

- 收到 generate job 后：
  1. 根据 `adapter/platform/account_id` 找到绑定角色。
  2. 根据 `adapter/platform/account_id/session_id` 查找 chat 绑定。
  3. 如果没有 chat 绑定，自动为该角色创建新 chat。
  4. 新 chat 名称使用：`[AstrBot] {platform}-{session_display_name}-{session_id短码}`。
  5. 保存 `adapter/platform/account_id/session_id → character_id + chat_id`。
  6. 将 AstrBot 用户消息追加到该 chat。
  7. 调用 SillyTavern 内部生成能力。
  8. 返回 `generate_result` 或 `generate_error`。

## 配置

### AstrBot 插件配置

```yaml
bridge:
  mode: "embedded"
  host: "127.0.0.1"
  port: 8008
  timeout_seconds: 120

behavior:
  default_enabled: true
  fallback_message: "RP 后端暂时不可用。"
```

`bridge.host` 第一版默认并建议保持 `127.0.0.1`。第一版不做认证，不应暴露到公网。

### SillyTavern 扩展配置

```json
{
  "bridgeUrl": "ws://127.0.0.1:8008/ws",
  "accountBindings": [
    {
      "adapter": "aiocqhttp",
      "platform": "qq",
      "accountId": "123456",
      "characterId": "alice"
    }
  ]
}
```

扩展自动维护 chat 绑定：

```json
{
  "chatBindings": {
    "aiocqhttp:qq:123456:astrbot-session-id": {
      "characterId": "alice",
      "chatId": "..."
    }
  }
}
```

`accountBindings` 由用户配置，`chatBindings` 由扩展自动创建和维护。

## WebSocket 协议

### hello

扩展连接后发送：

```json
{
  "type": "hello",
  "client": "sillytavern-extension",
  "version": "0.1.0"
}
```

Bridge Server 返回：

```json
{
  "type": "hello_ack",
  "server": "astrbot-smarter-rp",
  "version": "0.1.0"
}
```

### generate

AstrBot 插件创建 job 并发送：

```json
{
  "type": "generate",
  "jobId": "uuid",
  "adapter": {
    "name": "aiocqhttp",
    "platform": "qq",
    "accountId": "123456"
  },
  "session": {
    "id": "astrbot-session-id",
    "displayName": "测试群"
  },
  "user": {
    "id": "user-456",
    "name": "Alice"
  },
  "message": {
    "text": "今晚剧情继续吗？"
  }
}
```

### generate_result

扩展生成成功后返回：

```json
{
  "type": "generate_result",
  "jobId": "uuid",
  "reply": "当然，我们从上次的场景继续……",
  "characterId": "alice",
  "chatId": "chat-id"
}
```

AstrBot 插件只依赖 `reply`，其它字段只用于日志和排错。

### generate_error

扩展生成失败后返回：

```json
{
  "type": "generate_error",
  "jobId": "uuid",
  "code": "missing_character_binding",
  "message": "No character binding for aiocqhttp:qq:123456"
}
```

AstrBot 插件不向聊天窗口暴露内部错误，只回复 fallback。

## 并发和超时

第一版使用全局串行生成：

```text
一次只处理一个 generate job
```

这样可以避免 SillyTavern 当前角色、当前 chat 或生成状态被并发请求污染。后续确认扩展能安全隔离上下文后，再考虑升级为同一 chat 串行、不同 chat 并发。

超时流程：

- AstrBot 插件创建 job 后等待 `bridge.timeout_seconds`。
- 超时后删除 pending job，回复 fallback。
- 扩展晚到的 result 被丢弃。
- 扩展返回 `generate_error` 时立即回复 fallback。

## 错误处理

AstrBot 插件 fallback 场景：

- SillyTavern 扩展未连接。
- Bridge Server 无法启动。
- adapter/account 没有绑定角色卡。
- 自动创建 chat 失败。
- SillyTavern 生成失败。
- WebSocket 断开。
- job 超时。
- result 缺少非空 `reply`。

扩展侧应该为可诊断失败返回 `generate_error.code`，插件侧记录日志但不向用户暴露内部细节。

## 安全边界

第一版不做认证，因此必须默认限制为本机通信：

```text
127.0.0.1 only
```

文档必须明确：不要把 Bridge Server 暴露到公网；如果未来需要远程 SillyTavern，需要单独设计认证、反向代理、HTTPS 和防火墙规则。

## 测试重点

AstrBot 插件侧：

- 没有扩展连接时返回 fallback。
- 扩展连接后能收到 generate job。
- 扩展返回 `generate_result` 后回复原平台。
- 扩展返回 `generate_error` 后 fallback。
- 超时后 late result 被丢弃。
- `/rp off` 时不创建 job 并放行原流程。
- `/rp on` 后恢复 job 创建。

SillyTavern 扩展侧：

- 没有 account binding 时返回 `missing_character_binding`。
- 同一 `adapter/account/session` 复用同一 chat。
- 新 session 自动创建新 chat。
- 不同 adapter/account 不会串 chat。
- 自动 chat 名称符合 `[AstrBot] {platform}-{session_display_name}-{session_id短码}`。

## 第一版成功标准

- 用户只需要在 SillyTavern 扩展里配置 account 到角色卡的绑定。
- AstrBot 新 session 不需要手动绑定 chat，会自动创建并复用。
- AstrBot 消息能经 WebSocket 进入 SillyTavern 扩展生成。
- SillyTavern 生成的 reply 能回到 AstrBot 原平台。
- 后端不可用、未绑定角色、生成失败或超时时都有 fallback。
- 项目文档清楚说明第一版只支持本机、无认证、全局串行。
