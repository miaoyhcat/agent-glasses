# 验证报告 / v0.2

**没有完整眼镜实物。** 软件运行、数字设计检查与工程计算分开记录。验收以程序输出、源文件哈希和明确试验条件为依据。

| 等级 | 含义 | 当前边界 |
|---|---|---|
| 1 已实测通过 | 可复核硬件实测 | 0项，没有称重、光学、续航、佩戴或安全实测 |
| 2 已通过软件测试或仿真 | 实际程序、编译、CAD、虚拟Android | 下表只对具体范围有效，不自动证明产品性能 |
| 3 已通过工程计算或文献论证 | 可复算模型或原始资料 | 输入假设不等于实物指标 |
| 4 待实物验证 | 仍缺实体/目标平台/供应商验证 | 包括完整目标Docker与真机链路，不能改称已通过 |

## 本轮实际检查

| 检查 | 证据 | 可得出的结论 |
|---|---|---|
| 主机测试 | software-validation.json / unit-tests.txt | 62项；认证、状态、媒体幂等与恢复、stdio模型中转及限额等通过 |
| HTTPS模拟闭环 | https-demo.json | 11个功能断言；真TLS，明确模拟智能体，没有真实拍摄 |
| Android共享音频代码 | java-audio-tests.json | 7项真实PcmWave类JVM断言 |
| Android共享可靠性代码 | java-reliability-tests.json | 13项断言；慢轮询、独立取消、有界队列、最新HUD、原子写/恢复/并发读取 |
| 固件共享原生函数 | native-core-tests.json | 256组128位base32向量与独立RFC4648实现一致；SPIFFS路径和HUD映射通过 |
| D0固件 | firmware-validation.json | N16R8交叉编译；RAM34132B，程序695421B；没有烧录 |
| P1 T-Glass V2固件 | 同上 / tglass-v2-build.txt | QSPI PSRAM/4MB目标编译；RAM63212B，程序706261B；没有光学实物 |
| Android构建与运行 | android-build.txt / android-runtime.json | 以报告中APK哈希为准；API26实际安装、TLS配对、任务发送/审批/状态显示；智能体是模拟端 |
| 签名重试反例 | android-runtime-signing-attempt.json | 中间测试包与恢复的原交付签名不一致，安装被Android拒绝；只清理临时AVD测试数据后重新验证，不卸载个人手机数据 |
| 模型中转 | test_model_broker.py | 真子进程与HTTP流/ACK；上游为明确测试对端；长期密钥不进入worker消息；Docker本身未运行 |
| CLI0.162.1 | codex-live-probe.json / codex-schema-check.json | 实际schema、初始化与配置读取；本环境thread/start未完成 |
| 本地真实Codex实验 | local-codex-broker.json | 诊断性0.104.0+本地Qwen经受限MCP读取/失败测试/写入/成功测试，独立2项测试通过；仅公开样例 |
| 交付脚本真实复现 | local-codex-reproduction.json | 修正runner仅复制两样例文件后，5次真实模型请求，独立2测试通过；与第一次同补丁 |
| 目标电脑预检 | codex-target-preflight.json | 缺Docker与模型API凭据，完整生产路径验收未通过 |
| 安装包独立导入 | wheel-runtime.json | wheel在隔离解释器中从新虚拟环境导入，版本0.2.0，工作台资源存在 |
| 连续任务权限边界 | unit-tests.txt / test_worker_tree.py | 拒绝符号链接/硬链接/特殊文件；禁止旧worker未清理时重用副本；不证明真实Docker隔离 |
| 独立样例验收防伪 | test_acceptance_staging.py | 固定测试和安全AST；排除模型创建的unittest.py、旧pyc及符号链接 |
| 结构装配 | cad-build.json / cad-assembly-check.json | 有效BREP；STEP零件10组交叠为0；旧位置123.9285mm³/侧为负例 |
| 联锁测试板 | interlock-netlist-check.json / interlock-drc.txt | 原理图/47焊盘/10网一致，0 error/0 unconnected；18库元数据warning；不是电气行为验证 |

报告文件位于docs/evidence；测试源码位于tests。完整路径、输入和限制见evidence-index.json。之前的实验失败记录保留，不覆盖为通过。Android35镜像未达到启动验收；不能说API35运行通过。调试APK签名不是正式发布身份。

## 真实任务状态的反例

模型可以产生真实turn/completed而没有执行正确修改。一次本地实验确实遇到这种情况：只有工具调用样式的文字，独立检查不通过。公共completed只表示回合结束；默认verification_status=not_verified。命令exit=0也不自动证明全部测试或产品验收通过。

最新实际本地实验结论以local-codex-broker.json中的passed、minimal_patch_security_guard和independent_test_exit为准。一次严格AST检查最初因模型删除文档字符串而拒绝；保留原报告，再用去掉文档字符串后仍完整匹配的安全AST独立重验，测试通过。没有执行任意模型代码。没有Docker的本地诊断不等于Windows/WSL2或生产容器验收。完整同会话inspect→fix→test另由scripts/accept_codex_worker.py在目标电脑执行。

## 工程计算

完整H1质量预算66.45g，50g目标未达；49.65g独立分项最低值不是可达性证据。简化静力模型鼻部承重约81%，不是舒适证明。

450mAh/1.665Wh，90%可用、80%寿命末期、88%转换效率：混合8.486h、重显示3.538h、连续HUD4.190h。混合73%为连接待机，光机再增加150mW时降为约6.97h。D0/P1没有实现该模型所需低功耗调度。录像1.053h只是能量上限，热设计不支持照此连续录制。

近轴640×480/约20°不是光学处方或光线追迹。热模型是集中参数敏感性，不是FEA；35°C环境下一些状态超过内部40°C接触目标。不能进行已合格通电佩戴声明。

## 复现

~~~bash
python -m pip install -e .
python scripts/verify.py
python scripts/build_firmware.py
python scripts/build_android.py --sdk 官方SDK目录
python scripts/check_android_runtime.py --sdk 官方SDK目录 --api 26 --boot-timeout 420
python scripts/build_cad.py
python scripts/check_cad_assembly.py
python scripts/check_interlock.py
~~~

KiCad检查需匹配的pcbnew与kicad-cli；Android需官方运行镜像。构建源和输出哈希见build-manifest.json。不同平台字节完全相同的可重现构建没有证明；GitHub远程CI未运行。完整实物验收方法在acceptance-matrix.csv，不因文档或模拟而自动通过。

实际本地模型实验的复现方式、失败记录与受限范围见 [公开样例说明](../agent-integration/codex/local-benchmark.md)。新runner的第一次运行因复制README而被排他文件守卫拒绝；修正为仅复制两个受信样例文件，未扩大工具权限。
