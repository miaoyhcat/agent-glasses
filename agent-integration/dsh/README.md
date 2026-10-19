# DSH（DeepSeek Harness）接入

DSH 和 Codex 走**同一条链路**，区别只在隔离 worker 里跑哪条命令行：

```
眼镜（显示/采集）←→ 手机（语音/转写/网络）←→ 电脑连接器（身份/授权/审批）
                                                    ↓
                                              隔离 worker（无外网 Docker）
                                                    ↓
                                          codex app-server  或  dsh ...
```

模型密钥留在电脑端；任务进度取自真实会话事件；容器内没有外网出口。

## 怎么接

worker 默认启动 Codex。要换 DSH，给两个环境变量即可，**不用改代码**：

```bash
AGENTGLASS_AGENT=dsh \
AGENTGLASS_AGENT_ARGS="<DSH 的等价启动参数>" \
python3 agent-integration/codex/worker_entry.py
```

- `AGENTGLASS_AGENT`：要启动的可执行文件（默认 `codex`）。
- `AGENTGLASS_AGENT_ARGS`：按空格切分的启动参数；非 Codex 分支不会注入任何
  Codex 专有配置（`-c model_provider=...` 那些只对 Codex 生效）。

## 需要 DSH 一侧满足的前提

1. **帧协议**：worker 按「一行一个 JSON 对象」在 stdin/stdout 上转发，
   形如 `{"channel":"codex","payload":{...}}`。DSH 若不提供等价的
   app-server 式 JSONL 会话，需要先写一层薄适配脚本，把 DSH 的事件转成
   同样的帧。
2. **模型指向**：worker 期望 agent 的模型请求打到本机 broker
   `http://127.0.0.1:9041/v1`（Codex 用 `model_provider` 指过去）。
   DSH 侧要对等配置，把 base URL 指到同一处、密钥用 broker 下发的令牌。
3. **只读/写边界**：`inspect` 只跑在副本上；`fix`/`test` 需要 `allow_write`
   加成并逐任务在本机批准。这条约束在协议层，不由 agent 自己决定。

## 验证状态

| 项 | 状态 |
|---|---|
| Codex 路径（默认分支） | 已按实测 0.162.1 的 schema 接入，见 [Codex 接入说明](../codex/README.md) |
| worker 换命令的入口（`AGENTGLASS_AGENT`） | 已实现，默认分支行为不变 |
| **DSH 真机联调** | **未做** —— 没有在真实 DSH 上跑过，DSH 的启动参数与帧格式以它自己的文档为准 |

没跑过就写没跑过。等你在本机接上以后，把实际参数补回这份文档即可。
