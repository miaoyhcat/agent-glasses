# 公开样例：真实Codex与本地模型复现

这是**已实际运行的受限兼容诊断**，不是模拟模型，也不是生产系统的通用修复验收。官方CLI0.104.0、Ollama0.40.5、qwen3:4b-instruct，经本项目真实stdio模型broker和MCP工具完成：读取原始代码 → 固定测试失败 → 模型写入修复 → 固定测试通过。两次独立任务得到同一补丁；实际交付复现脚本也完成一次完整通过。独立Python进程确认两项测试通过，测试源字节不变。

## 为什么受限

本执行环境的官方CLI0.162.1初始化/配置读取可用，但thread/start超时。0.104.0可建立会话；原生shell的嵌套沙箱启动失败。因此没有关闭沙箱，也没有开放宿主任意shell：改为固定MCP工具仅访问两个公开样例文件。写入必须与原完整AST一致，仅允许折扣运算符与文档字符串变化；测试固定、路径固定、调用有上限。这里的成功不能推导为任意项目修复能力或Docker安全性。

`fixture_mcp.py`提供read_fixture/write_fixture/test_fixture，真实MCP初始化、tools/list和tools/call由官方CLI完成。独立测试使用隔离Python、新缓存路径，防止一秒内同大小补丁误用旧pyc。模型文字或completed不会改变passed。

## 在可丢弃的公开测试环境运行

需要预先取得指定官方CLI、Ollama和本地模型权重；本仓库不分发它们，也不自动下载。模型约2.5GB，CPU推理需要足够内存和时间。CLI0.104.0仅作为这里的兼容诊断版本，**真实私有项目使用主指南的当前版本、受限Docker与目标验收**。

```bash
python -m pip install -e .
# 模型已由官方Ollama取得且在本地缓存后；每次使用新的输出目录：
python scripts/benchmark_codex_local.py \
  --codex /absolute/path/to/codex \
  --ollama /absolute/path/to/ollama \
  --models /absolute/path/to/ollama/models \
  --output build/public-model-check-1 \
  --public-disposable-environment
```

脚本启动仅loopback的本地Ollama，禁止其cloud模式，关闭CLI遥测/导出器及非必要远程能力，将非loopback HTTP(S)代理指向关闭的端口，拒绝继承启用的额外MCP。它没有宿主/容器安全认证能力，不能在含私密文件的日常电脑上代替生产隔离；CLI仍存在自身只读shell能力，工具授权以公开可丢弃环境为边界。API主密钥不用于实验，模型代理的key为明确的本地占位值。

## 结果与失败证据

- `docs/evidence/local-codex-broker.json`：第一次接受的真实任务；原精确AST检查因文档字符串删除而拒绝，保留旧报告，再用严格保留可执行AST的独立检查验收。
- `docs/evidence/local-codex-reproduction.json`：**交付脚本本身**实际执行；5次真实本地模型请求，真实MCP工具审计、独立exit=0及源哈希。
- `docs/evidence/local-codex-reproduction-tests.txt`：独立两个测试的真实输出。
- `examples/verified-local-result/discount.py`：实际模型补丁，不用于电脑服务运行。
- `docs/evidence/local-benchmark-initial-attempt.json`：新runner第一次错误复制README，排他样例守卫拒绝连接；修正为只复制两文件，没有放宽权限。
- 其他thinking/unified-exec/严格AST失败记录保留。不得只公布成功而隐去这些边界。

通过条件是completed、真实写入工具、真实成功测试、安全AST和独立测试同时成立。目标生产链路仍需运行`accept_codex_worker.py`，其OpenAI API/Docker路径没有在本环境通过。
