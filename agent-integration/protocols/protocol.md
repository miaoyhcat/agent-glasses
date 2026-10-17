# AgentGlass Protocol 1

本协议是本项目自己的配件协议，不冒充 Codex API。桌面端通过官方 App Server 的 JSONL stdio 调用 Codex。

## HTTPS 控制平面

所有路由强制 TLS ≥ 1.2。Android 用带外核验的证书 DER SHA-256 指纹锁定整张证书；CLI 用本地证书信任。更换证书必须重新核验指纹。除 `/health`、首页和 `/v1/pair` 外，必须发送 `Authorization: Bearer <256-bit-token>`。禁止 URL 中的令牌。没有公网上的 Codex 原始端口。

| 路由 | 内容 / 返回 |
|---|---|
| POST /v1/pair | `{code,name}`；单次、300 秒码；返回设备令牌 |
| GET /v1/projects | 本机配置的项目 ID，不泄露绝对目录 |
| POST /v1/tasks | `{v:1,request_id,project,action,prompt,parent_task_id?}`；action=inspect/fix/test |
| GET /v1/tasks | 最新 100 个任务，不包含源文件或原始日志 |
| GET /v1/tasks/{id} | 真实任务状态、实际 thread_id/turn_id、持久 last_summary、来自真实事件的 progress_text/progress_event_seq；verification_status 默认 not_verified |
| POST /v1/tasks/{id}/cancel | 请求中断；只有官方完成事件才记作已取消 |
| GET /v1/events?after=N | 单调 seq、最多 200 条；返回 cursor；断线从最后 cursor 继续 |
| GET /v1/operator/pending | 限 loopback + 独立 operator 令牌，含完整待批准指令 |
| POST /v1/operator/tasks/{id}/decision | 本机 approve/reject；批准必须确认副本和模型服务数据处理 |
| POST /v1/media | `{size,sha256,mime,request_id?}`；设备内幂等，返回 ID/offset/complete |
| GET /v1/media/{id} | size/received/complete |
| PUT /v1/media/{id}/chunks?offset=N | 顺序原始字节块，≤256KiB；精确重复可安全重传 |
| POST /v1/media/{id}/commit | 长度和 SHA-256 匹配后提交；返回完整状态 |
| POST /v1/ai | 已提交media_id、kind=transcribe/vision、question、consent_upload_and_cost=true；默认拒绝云服务 |

`request_id` 在同一设备内幂等。重复 ID + 相同参数返回原任务；参数不同返回 400，不能启动第二次。任务不会因断线自动重放。HTTP 401=重新配对或令牌撤销；403=权限不足；429=退避重试；其他 400=修正请求后重试。首次实现针对一个个人所有者，所有已配对设备共享该所有者的任务历史；**不是多租户服务**。媒体资源限定上传设备。

parent_task_id只接受同项目已完成任务；每个继续任务仍须本地批准，复用原副本和真实会话。/v1/ai不是幂等付费接口，不自动重试；必须由本机开启且每次请求明确同意，默认每天最多20次。

状态流：pending → preparing → running → completed/failed/cancelled。cancel_requested 是请求状态；服务重启或丢失完成证据为 unknown。完成不能凭耗时推算。UI 不显示猜测的百分比，不把命令退出码 0 自动称为“所有测试通过”。对外暴露公开 plan、item 类型/生命周期/退出码、agentMessage；过滤全部 reasoning、任意工具参数和原始工具输出。

## 眼镜 BLE / USB 帧

BLE 服务 `6e400001-b5a3-f393-e0a9-e50e24dcca9e`，RX 写 `...0002...`，TX 通知 `...0003...`。USB 使用同样 LF 分帧的消息；USB 仅作调试/首次本地配置。每条消息 <4096 字节；BLE 请求 MTU247；按 min(180, 实际MTU−3) 字节切片，协商失败回退20字节，LF 才执行，超长清空缓存。HMAC key 32 字节首次用受信任 USB 串口写入。应用层 HMAC 提供指令身份认证，不提供链路保密；BLE 设备必须先完成带显示密码的加密绑定，未绑定不开放敏感媒体操作。

上电设备发 `{v:1,type:"hello",session:"<32 lowercase hex>",...}`。session 每次启动随机，seq 在该 session 内严格递增。主机形成 **原样 body 字符串**，计算：

```
hex(HMAC-SHA256(key, utf8(session + "\n" + decimal(seq) + "\n" + body)))
```

封套 `{v:1,seq:1,body:"{\"op\":\"status\"}",mac:"..."}`，末尾 LF。认证失败不改变 seq。认证成功、参数不合法的命令仍消耗 seq，防止重放。不存在任意 Lua/shell/文件路径执行操作。

| op | 功能 |
|---|---|
| hud | `bitmap`：128×64、MSB-first、1024 字节单色位图 Base64；手机负责中文字体栅格化 |
| photo | 前置物理开关与 LED 电气门控通过后采 JPEG，先写本地再发通知 |
| record | `seconds`=1..15，JPEG 帧容器，非 H.264；失败/存储满显式报错 |
| audio | `seconds`=1..8，本地 16kHz PCM WAV；不宣称已实现离线自然语言 ASR |
| speaker_start / speaker_data / speaker_play | 最多256000字节16kHz PCM16单声道；先声明长度和SHA-256，顺序384字节块，设备逐块返回speaker_ack.offset，完整校验后播放；30秒无新块丢弃缓存 |
| list | 本地未确认媒体元数据 |
| read | 仅 26 字符小写 Base32 或旧版 1–10 位数字 ID、offset；每次返回 ≤384 字节 Base64 和偏移 |
| ack | ID + SHA-256，主机持久化并核验后确认，才允许删本地缓存 |
| sleep | 关显示、关摄像头、睡眠；物理按钮唤醒 |
| status | 当前电源/缓存/摄像状态；未知电量用 null，不伪造百分比 |

status可带unix与tz_minutes，经认证后校时；超出支持范围拒绝。短语音是接收完整片段后播放，不是已证明低延迟的连续流。

固件实际支持范围和移植状态见 `firmware/README.md`。本协议没有把尚未完成的光机驱动当作已实现。

## v0.2 可靠性和真实模型边界

Android 在第一次媒体初始化请求之前将随机 `upload_request_id` 持久化；HTTP 字段名为 `request_id`。同设备、同 ID 和同内容返回原媒体及已接收偏移；参数冲突拒绝，其他设备不可查询。设备 BLE 媒体 ID 与桌面 UUID 是不同命名空间，手机保存两者映射。手机使用临时文件、文件 fsync、原子重命名、目录同步及 SHA-256 后才发设备 ack；掉电测试仍未执行。

`completed` 仅表示官方 `turn/completed` 已收到。它不证明代码修复正确；对外 `verification_status` 默认 `not_verified`，智能体文字和工具输出不能将其提升为验证通过。独立验收脚本另行执行固定测试，保留真实退出码。`worker_cleanup_confirmed` 只有实际执行容器删除命令并确认成功才为 true。

手机对轮询使用 single-flight，对 HUD 使用 latest-only，对取消使用独立有界队列；切换目标电脑后旧连接响应不可提交到新连接。UI 仍为前台工程原型，未完成后台服务和完整 BLE 重连验收。

### 桌面到隔离工作进程（不是眼镜协议）

容器固定 `--network=none`。官方 Codex App Server 的 JSONL 被固定 Python 入口封装为 `channel=codex`；只允许回到桌面模型代理的帧为 `channel=model`。每个任务短期 token、请求个数/体积/输出上限、模型白名单均由桌面执行。真实 API key 只在桌面，未写入容器。代理没有宿主 TCP 监听端口，固定上游为 OpenAI HTTPS Responses；响应按序号 Base64 分块，工作进程消费后 ACK，阻止无限缓冲。

工作进程内部 loopback HTTP 是 Codex provider 的适配接口，不能直接从手机访问。stdio 封套不是 Codex 官方协议的一部分，官方 `initialize/thread/start/turn/start/turn/completed` 保持原结构。详见 [真实接入指南](../codex/README.md) 和 [安全边界](../../SECURITY.md)。容器规则有软件测试；真实 Docker 隔离验收尚未执行。

跟进任务的本机批准在旧worker未退出/清理未确认或同副本runner仍活动时拒绝；对外返回通用400，不泄露宿主文件细节。链接/硬链接/特殊文件副本不进入权限重新分配。
