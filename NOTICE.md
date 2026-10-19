# 原创与第三方边界

本项目原创内容使用 [个人非商业使用许可证](LICENSE)，商业联系 **3277681859@qq.com**。该限制不覆盖第三方自身作品的合法授权范围。项目不是 OSI 定义下的开源项目。

仓库交付包不包含完整数据手册、工具链、Codex二进制、模型权重、Android系统镜像、Arduino框架或供应商CAD。唯一保留的第三方源码子集为third_party/lilygo-tglass-v2内的八份原厂MIT显示驱动/许可文件，其原始版权和哈希均已保留。`hardware/mechanical/generated` 是本项目自己的封装夹具模型，光机方块是询价包络，不能当作供应商实际结构图。PCB 中的封装由生成脚本按数据手册尺寸自行绘制，尚需独立封装审核。

| 依赖 / 外部资料 | 原始许可证 / 使用条件 | 本仓库的处理方式 |
|---|---|---|
| OpenAI Codex CLI / App Server | 上游 Apache-2.0；模型服务另有服务条款 | 固定版本 0.162.1，运行时另行安装，不重新授权 |
| Arduino-ESP32 / ESP-IDF | 上游分别包含 LGPL-2.1、Apache-2.0 及各组件许可 | 由 PlatformIO 获取；不在交付包再分发固件二进制或工具链 |
| ArduinoJson 6.21.5 | MIT | 声明依赖；不把其自身改为非商业许可 |
| NimBLE-Arduino 1.4.3 | Apache-2.0，底层组件另有通知 | 声明依赖；原始通知以下载包为准 |
| aiohttp / cryptography | Apache-2.0；cryptography 同时有 BSD 等声明 | pip 依赖；保持第三方包自己的许可 |
| Brilliant SDK / 硬件资料 | 以对应上游仓库和器件条款为准 | 可选 HUD 适配，不复制厂商固件或声称本项目拥有厂商设计 |
| LILYGO T-Glass V2驱动 | MIT，2023/2024 ShenZhen XinYuan/LilyGo | 八份文件原样保留；ORIGIN.json记录来源与哈希，不重新授权上游作品 |
| Android SDK / 系统接口 | Android SDK 协议与组件原许可 | 原生应用调用系统 API；SDK 不打包进项目 |
| KiCad / CadQuery / OpenSCAD | 上游 GPL、Apache-2.0、GPL 等各自许可 | 用作设计工具；不改变工具的许可；产出是本项目原创设计 |
| 厂商手册、专利、论文、产品页 | 各权利人的版权、专利及访问条款 | 只提供事实摘要、索引和链接；不提供专利实施许可 |

如将来发布链接第三方库的固件二进制，必须逐项处理所用库的分发、通知、源代码和重链接义务，特别是 LGPL 组件。当前提供编译记录和完整原创源码；编译出的固件可由个人依据工具链自行复现。Android APK 为本项目原生调试构建，使用独立调试签名，不是生产发行签名。

商标名称仅用于识别兼容性和资料来源。CodexGlasses 未获 OpenAI、Meta、Brilliant Labs、Rokid、Espressif 或其他提及公司的官方认证或背书。数据手册和代码可见不等于获得专利或光学模组制造许可。
