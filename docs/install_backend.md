# Browserless Tavern 后台模式安装指南

默认模式不再依赖浏览器扩展。插件会在 AstrBot 进程内通过本机 HTTP 调用 SillyTavern，并提供本机 WebUI 管理角色卡、世界书和账号绑定。

## AstrBot 插件安装

把本仓库放到 AstrBot 的插件目录中，目录名保持为 `astrbot_plugin_smarter_rp`，然后在 AstrBot 插件管理中启用 `smarter_rp`。

## 安装本地 SillyTavern

运行仓库内脚本安装 SillyTavern：

```bash
scripts/setup_sillytavern.sh
```

脚本默认把 SillyTavern 安装到：

```text
~/.local/share/astrbot-smarter-rp/SillyTavern
```

SillyTavern 是通过脚本安装到本地目录的上游项目，不 vendored 到本插件仓库。SillyTavern 使用 AGPL-3.0 License；部署和修改 SillyTavern 本体时请遵守其许可证要求。

## 默认配置

```yaml
tavern:
  mode: "managed"
  host: "127.0.0.1"
  port: 8001
  base_url: "http://127.0.0.1:8001"
  install_dir: "~/.local/share/astrbot-smarter-rp/SillyTavern"
  auto_start: true
  startup_timeout_seconds: 60
  request_timeout_seconds: 120
  auth:
    enabled: false
    username: ""
    password: ""
    token: ""
webui:
  enabled: true
  host: "127.0.0.1"
  port: 8010
  token: ""
behavior:
  default_enabled: true
  fallback_message: "RP 后端暂时不可用。"
```

`tavern.mode: managed` 是默认路径。启用后插件会：

1. 创建本地 SillyTavern HTTP client；
2. 在 `tavern.auto_start: true` 时启动 `tavern.install_dir` 中的 SillyTavern；
3. 启动 browserless TavernWorker 处理 AstrBot 消息；
4. 在 `webui.enabled: true` 时启动本机 WebUI。

所有监听地址必须保持 `127.0.0.1`、`localhost` 或 `::1`，不要暴露到公网。

## WebUI 使用

默认 WebUI 地址：

```text
http://127.0.0.1:8010
```

WebUI 始终需要 token。建议为长期运行的实例显式设置一个随机 `webui.token`；如果保持为空，插件会在本机插件数据目录生成 `webui_token.txt`，可在 AstrBot 中使用 `/rp webui` 查看 WebUI 地址和 token 文件路径。

WebUI 可用于：

- 查看 SillyTavern 状态；
- 导入角色卡；
- 导入世界书；
- 配置 `adapter/platform/account_id → character_id` 账号绑定。

## 角色卡、世界书和绑定流程

1. 运行 `scripts/setup_sillytavern.sh`，确认 SillyTavern 能在本机启动。
2. 在 SillyTavern 中配置可用的模型后端/API。
3. 打开 WebUI，导入角色卡；如需要世界书，在 WebUI 导入世界书。
4. 在 WebUI 的绑定页面选择当前 AstrBot 账号对应的 `adapter`、`platform`、`account_id` 和角色 ID。
5. 也可以在 AstrBot 中使用备用命令：
   - `/rp bind <character_id>`：绑定当前账号到角色；
   - `/rp binding`：查看当前账号绑定；
   - `/rp unbind`：删除当前账号绑定；
   - `/rp on` / `/rp off`：启用或停用当前会话 RP。
   - `/rp webui`：查看 WebUI 地址和默认生成 token 的本机文件路径。
6. 首次收到会话消息时，插件会自动创建 SillyTavern chat，名称格式为 `[AstrBot] {platform}-{session_display_name}-{session_id短码}`，之后复用同一 chat。

## 故障排查

- AstrBot 返回 fallback：确认 SillyTavern 已启动、模型后端可用，并且当前 AstrBot 账号已绑定角色。
- 提示缺少角色绑定或一直 fallback：在 WebUI 或 `/rp bind <character_id>` 中绑定当前账号。
- 角色找不到：确认绑定的 `character_id` 是 SillyTavern 当前角色列表中的索引。
- 生成返回空内容：确认 SillyTavern 已配置可用模型后端/API。
- SillyTavern HTTP 端口占用：修改 `tavern.port` / `tavern.base_url`，并确认仍为本机地址。
- WebUI 端口占用：修改 `webui.port`，并确认 `webui.host` 保持本机监听。
