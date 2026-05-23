# SillyTavern 扩展安装指南（Legacy / Manual Fallback）

当前默认推荐使用 browserless 后台模式，见 `docs/install_backend.md`。本扩展路径仅作为 legacy/manual fallback 保留：只有显式配置 `tavern.mode: "legacy_ws"` 时，主插件才会启动旧 WebSocket Bridge Server 并等待浏览器中的 SillyTavern 扩展连接。

## 何时使用 legacy 扩展

仅在以下情况使用：

- 你需要手动打开浏览器中的 SillyTavern 页面来处理生成；
- browserless HTTP 路径无法满足当前环境；
- 你明确希望继续使用旧扩展和 WebSocket Bridge。

启用 legacy 模式：

```yaml
tavern:
  mode: "legacy_ws"
bridge:
  mode: "legacy_ws"
  host: "127.0.0.1"
  port: 8008
  timeout_seconds: 120
```

本插件的 legacy 显式规则是：只有 `tavern.mode: "legacy_ws"` 时使用旧 BridgeServer。默认 `tavern.mode: "managed"` 会走 browserless TavernWorker，不需要浏览器扩展。

## 安装扩展

可以运行仓库内脚本搭建本地 SillyTavern 并安装扩展：

```bash
scripts/setup_sillytavern.sh
```

脚本默认把 SillyTavern 安装到 `$HOME/.local/share/astrbot-smarter-rp/SillyTavern`，并复制扩展到：

```text
public/scripts/extensions/third-party/astrbot-smarter-rp
```

也可以手动把本仓库目录 `sillytavern_extension/astrbot-smarter-rp` 复制到 SillyTavern 的第三方扩展目录。

启动或刷新 SillyTavern 后，在 Extensions 面板中启用 `AstrBot Smarter RP Bridge`。

## 配置步骤

1. Bridge URL 填写：`ws://127.0.0.1:8008/ws`。
2. 填写 account binding：
   - Adapter：AstrBot payload 中的 adapter name，例如 `aiocqhttp`。
   - Platform：平台名，例如 `qq`。
   - Account ID：机器人账号 ID。
   - Character ID / index：SillyTavern 当前角色列表中的角色索引。
3. 点击 Add binding 保存绑定。
4. 点击 Connect。

需要并行处理多个 AstrBot 对话时，在同一浏览器 profile 中打开多个 SillyTavern 页面即可让多个扩展连接到同一个 Bridge；每个页面内部仍会串行处理自己的任务，避免当前 chat 状态互相覆盖。

## 自动 chat 绑定

新的 AstrBot session 首次发消息时，扩展会自动创建 chat，名称格式：

```text
[AstrBot] {platform}-{session_display_name}-{session_id短码}
```

内部绑定依赖 `adapter/platform/account_id/session_id`，不依赖 chat 名称。

## 安全边界

Bridge URL 默认只连接 `127.0.0.1`。legacy Bridge 第一版没有认证，不要把 AstrBot Bridge Server 或 SillyTavern 扩展连接暴露到公网。
