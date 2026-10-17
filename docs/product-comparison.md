# AgentGlass 与代表性智能眼镜的对比

比较日期：2026-10-17。重点是使用场景、可修改性和智能体工作流，便于开发者选择平台。

| 产品 | 显示与采集 | 开发入口 | 实用侧重点 | 来源 |
|---|---|---|---|---|
| **AgentGlass** | H1单目HUD设计；P1近眼显示适配；D0相机/录音/短音频与手机协同 | 固件、Android、桌面、协议和CAD共同交付 | 自有项目上的inspect/fix/test、真实任务事件与本机审批 | [项目证据](evidence-index.json) |
| **Ray-Ban Meta Gen 3** | Camera + Audio型号；12MP相机、开放式音频 | 厂商应用及服务生态 | 第一视角记录、通话与日常助手 | [S62](https://www.ray-ban.com/usa/l/discover-ray-ban-meta-ai-glasses) |
| **Meta Ray-Ban Display** | 单目全彩600×600；12MP、麦克风与开放式扬声器 | Meta应用生态与Neural Band | 消息、字幕、导航与腕带交互 | [S63](https://www.ray-ban.com/usa/l/discover-meta-ray-ban-display) |
| **Rokid Glasses with Display** | MicroLED、30°FOV；12MP、4麦与开放式音频 | Rokid应用与服务 | 字幕、翻译、提词与拍摄 | [S64](https://store.rokid.com/products/rokid-glasses) |
| **Even Realities G2** | 双目绿光640×350、27.5°FOV；官方规格列4麦 | Even应用与设备体系 | 轻量信息提示、沟通辅助 | [S65](https://support.evenrealities.com/hc/en-us/articles/13499229138959-Specs) |
| **Brilliant Halo** | 彩色近眼显示；光学传感器、双麦与骨传导 | 公开Python/Flutter/Web Bluetooth及Lua接口 | 可编程应用与个人AI体验 | [S66](https://brilliant.xyz/products/halo) / [S67](https://docs.brilliant.xyz/halo/halo-sdk-python/) |
| **XREAL One Pro** | MicroOLED、57°FOV；Bose调校音频；XREAL Eye为外部配件 | USB-C DP主机与开发门户 | 电脑/游戏/移动设备大屏 | [S68](https://www.xreal.com/one-pro) |
| **RayNeo X3 Pro** | 双目全彩640×480、30°FOV；12MP、3麦阵列 | Creator Mode、Unity/Android ARDK | 导航、翻译、空间应用 | [S69](https://www.rayneo.com/products/x3-pro-ai-display-glasses) |

## AgentGlass 的实用价值

- **把任务带离电脑桌面**：为“检查项目→修复问题→运行测试”提供统一指令与状态接口，HUD呈现项目、阶段、结果和审批。
- **连接自己的开发环境**：桌面连接器可自托管，按本机配置授权项目；模型与设备入口分开配置。
- **让进度可核对**：状态由实际会话和公开事件产生，并提供测试记录与结果文件。
- **便于维护与二次开发**：从固件、手机、桌面到协议、BOM和CAD均在同一仓库，按个人非商业许可查看和修改。
- **面向日常信息的分布式设计**：手机承担字体、存储和网络，电脑承担开发任务，镜架侧聚焦采集、显示和交互。

## 对比口径

商业产品栏采用厂商公开规格；AgentGlass栏描述本仓库设计和实现，不是同条件整机实测排名。厂商未公开某个接口时，不推断其不支持第三方集成。Halo等产品同样具有公开开发生态；AgentGlass聚焦的是完整的Codex项目任务流程与可审查交付资料。

H1的66.45g、定义混合负载8.486h为工程预算；P1显示配置和H1参数分开记录。分辨率、视场、重量和续航不用于未经实测的“全面领先”结论。可复算输入见[可行性](feasibility-study.md)，软件运行记录见[验证报告](verification-report.md)。

可机读表：[CSV](product-comparison.csv) / [JSON](product-comparison.json)。更广的16款市场调研见[市场研究](market-research.md)，逐条资料与检索日期见[来源索引](sources.md)。
