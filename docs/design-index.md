# 设计图、原理图与配套资料总索引

从本页直接打开源文件、预览、物料与构建入口。文件属于同一AgentGlass仓库，修改后可按对应脚本重新生成。

## 电气与PCB

| 内容 | 可编辑源文件 | 预览、网表或制造审阅输出 |
|---|---|---|
| 相机状态联锁验证板原理图 | [KiCad原理图](../hardware/schematics/interlock.kicad_sch) | [SVG预览](../hardware/schematics/preview/interlock.svg) / [网表](../hardware/schematics/interlock.net) |
| 联锁验证板PCB | [KiCad PCB](../hardware/pcb/interlock-test-coupon/interlock-test.kicad_pcb) / [工程参数](../hardware/pcb/interlock-test-coupon/interlock-test.kicad_pro) | [Gerber、钻孔与作业文件](../hardware/pcb/interlock-test-coupon/fabrication-review/) |
| 电源与接口 | [电源树](../hardware/power/power-tree.md) / [引脚定义](../firmware/include/pins.h) | [连接表](../hardware/pcb/interlock-test-coupon/connections.csv) / [D0接线](../hardware/assembly/d0-wiring.csv) |

## 机械与光学

| 内容 | 源文件与输出 |
|---|---|
| H1结构参数 | [OpenSCAD](../hardware/mechanical/frame.scad) / [尺寸参数](../hardware/mechanical/parameters.json) / [质量布置](../hardware/mechanical/mass-placement.json) |
| 结构装配几何 | [装配STEP](../hardware/mechanical/generated/agentglass-h1-fixture.step) / [结构预览](../assets/packaging-fixture.png) |
| 前框 | [STEP](../hardware/mechanical/generated/front.step) / [STL](../hardware/mechanical/generated/front.stl) |
| 镜腿 | [STEP](../hardware/mechanical/generated/temple.step) / [STL](../hardware/mechanical/generated/temple.stl) |
| 盖板 | [STEP](../hardware/mechanical/generated/cover.step) / [STL](../hardware/mechanical/generated/cover.stl) |
| 光学与显示 | [光学说明](../hardware/optics/README.md) / [参数](../hardware/optics/specification.json) / [P1 T-Glass V2](../hardware/optics/p1-tglass-v2.md) |

## BOM、装配与预算

[器件BOM](../hardware/bom/components.csv) · [联锁板BOM](../hardware/bom/interlock-coupon.csv) · [质量预算](../hardware/bom/mass-budget.csv) · [成本预算](../hardware/bom/cost-budget.json) · [功耗负载](../hardware/power/budget.json) · [P1组成](../hardware/assembly/p1-components.csv) · [装配说明](../hardware/assembly/README.md) · [制造指南](manufacturing-guide.md)

## 代码、安装包与操作

| 模块 | 源码与教程 |
|---|---|
| 眼镜端D0 / P1 | [固件](../firmware/) / [构建与烧录](../firmware/README.md) |
| Android | [应用源码](../mobile/android/) / [手机指南](../mobile/README.md) |
| 桌面连接器 | [Python源码](../desktop/agentglass/) / [Codex接入](../agent-integration/codex/README.md) |
| 通信 | [设备与HTTPS协议](../agent-integration/protocols/protocol.md) |
| 演示 | [HTTPS模拟](../simulator/demo.py) / [真实本地模型样例](../agent-integration/codex/local-benchmark.md) |
| 安装包 | [APK与wheel](../releases/README.md) |
| 验证 | [报告](verification-report.md) / [证据索引](evidence-index.json) / [验收CSV](acceptance-matrix.csv) |

原理图/PCB条目按实际功能命名；图纸范围与测试范围由对应文件和证据记录定义。商业授权见[仓库授权页](../COMMERCIAL-LICENSE.md)。
