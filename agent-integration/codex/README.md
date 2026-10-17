# 官方Codex接入与目标电脑验收

使用官方App Server JSONL stdio，不存在本项目虚构的云端Codex任务接口。请求schema来自实际安装CLI0.162.1。当前环境初始化和配置读取可用，thread/start未完成；诊断性0.104.0可以建立会话并调用本地模型。具体结果与独立检查见docs/evidence，不能把任何模型回复或CLI退出码当成修复验收。

## 默认安全执行路径

电脑HTTPS连接器 → 官方RPC的stdio封装 → 无外网Docker worker → 官方Codex App Server。worker的模型HTTP请求通过同一stdio独立通道交给电脑broker；长期API密钥不进入容器。无需宿主模型监听端口、Unix套接字或账户认证文件挂载。

本版本实际提供的是**OpenAI API模型账户**接入；不把ChatGPT订阅认证文件当普通API密钥，也没有实现订阅OAuth代理。API账户、模型权限和费用由用户自己配置。

## 目标电脑配置（本轮未运行Docker）

Windows可研究Docker Desktop的Linux容器/WSL2；Linux使用Docker Engine。目标平台兼容必须实际验收。构建审核后的镜像：

~~~bash
docker build -t agentglass-codex:0.162.1-broker1 agent-integration/codex
~~~

镜像包含Python unittest、git、ripgrep与固定版本Codex。创建状态和授权项目后，在电脑本地config.json设置：

~~~json
{
  "runtime_isolation": "docker",
  "worker_image": "agentglass-codex:0.162.1-broker1",
  "allow_model_api": true,
  "codex_model": "账户实际可用的模型ID"
}
~~~

模型ID必须来自自己的账户，不从示例占位符推测权限。不要挂载auth.json。只在电脑进程提供OPENAI_API_KEY；不要保存到眼镜、手机、项目目录、命令参数或提交记录。可通过不回显输入启动：

~~~bash
python -c "import getpass,os;os.environ['OPENAI_API_KEY']=getpass.getpass('OpenAI API key: ');from agentglass.cli import main;main()" --state runtime serve
~~~

这不会自动发起模型任务。仍需手机提交、电脑本地批准。allow_model_api与ASR/视觉allow_paid_cloud分别控制。每任务8请求/4096输出token等限额见SECURITY.md，不是货币费用上限。

## 会话、取消与可见状态

inspect先复制授权项目；fix/test只作用于副本，需额外allow_write和本机逐任务批准。parent_task_id仅接受同项目已完成任务，复用实际thread与副本。唯一活动副本约束避免两个任务并发修改同一副本。旧v0.1认证挂载会话没有自动迁移，升级后开启新会话并保留原资料。

公开进度来自实际plan、命令/文件item类型、生命周期和退出码，以及用户可见agentMessage；reasoning、原始命令参数与原始工具日志不发送到眼镜。取消使用turn/interrupt；无完成证据显示unknown。Docker客户端退出后还会显式清理本任务唯一命名容器，并记录确认结果。

completed表示回合结束，默认verification_status仍为not_verified。模型可以给出不正确的自然语言回复，甚至只在文字里声称调用工具；独立验收必须识别这种情况。

## 可执行的完整验收

~~~bash
agentglass --state runtime doctor
python scripts/accept_codex_worker.py
# 明确同意真实模型费用后：
python scripts/accept_codex_worker.py --run --model 实际模型ID --acknowledge-model-cost --output build/live-check-1
~~~

无--run只检查前提，不调用模型，不返回虚假的验收通过。完整模式使用本项目公开折扣错误示例，经真实HTTPS建立绑定和本地批准，连续inspect→fix→test，检查同thread、原项目不变、测试文件不变和清理确认；最后仅将匹配安全AST的模块和可信原测试复制到干净目录，在另一个无网络/无凭据容器，以隔离Python和独立缓存跑固定测试，拒绝影子测试模块。每次使用新的输出目录，保留源码、日志和报告。该脚本已完成语法与无凭据预检；本环境没有运行完整Docker模式。

还须补测取消竞态、断网、容器崩溃、读宿主/原项目、联网、令牌泄漏与重启恢复。当前不提供无需审核即把副本修改合入原项目、发布或付费的路径。

公开样例的诊断性真实模型通过记录与可执行复现脚本见 [本地实验](local-benchmark.md)。0.104.0仅用于公开、可丢弃环境的兼容诊断，不是推荐给私有项目的版本。连续任务拒绝旧worker清理未确认及链接/特殊文件副本。bind mount的硬磁盘配额仍是目标验收门槛。
