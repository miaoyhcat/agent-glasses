# P1：使用完整光学设备先验证近眼交互

当前优先试制路线为 **P1：原厂 LILYGO T-Glass V2/H715 + Android + D0 台架采集 + 电脑连接器**。这是分体研发装置，没有达到普通眼镜外观、50g或8小时的H1产品验收。

官网H715本轮显示USD54.63、available=true [S53]；单独棱镜N276显示缺货。未下单或收到样品。采购必须核对V2、完整显示板和棱镜、4MB Flash/2MB QSPI PSRAM；不得套用V3的相机、扬声器或引脚参数。

JD9613 RAM为294×126，棱镜观察区约126×126，放大区还会缩小 [S54]。手机128×64 HUD映射到观察区中央；面板像素数不是实测可读像素、FOV或眼盒。

## 实现与构建

`firmware/src/tglass_main.cpp`包含原厂初始化、起始亮度16/255、显示窗口、数字时钟、认证校时、USB按键配置、加密绑定与HMAC。`hud_raster.h`的映射保留左右边缘并使用RGB565白色。Android增加独立T-Glass连接，可同时保留D0采集连接。

八份原厂MIT驱动/许可文件按提交99ae22477daeaec55714f6b31e0219407dd52439保留，哈希在`third_party/lilygo-tglass-v2/ORIGIN.json`，没有重新授权第三方代码。

原厂x/y `pushColors`封装存在坐标约定风险。本适配使用`setAddrWindow`和明确的**字节长度**发送，不调用该封装。起点采用原厂V2示例下部观察区；12ms间隔是待测发送余量，不是DMA完成证明。

```bash
python -m pip install platformio==6.2.0
python scripts/build_firmware.py --env codexglasses_tglass_v2
# 核对板型和USB端口后，POSIX shell：
PLATFORMIO_SETTING_ENABLE_TELEMETRY=no python -m platformio run -d firmware -e codexglasses_tglass_v2 -t upload
```

首次烧录后在受信任USB查看配对密码；按住BOOT发送`provision <64位十六进制密钥>`。密钥由用户安全随机生成，不放进仓库。Android选择“连接T-Glass近眼显示”，再连接电脑。双设备绑定、MTU、重连与中文显示均待实机验证。

首次通电固定于头模，检查启动、供电、视轴、倒像/镜像及DMA时序；确认光学安全条件后短时观察。16/255本身不是眼安全证明。按DISP-01/03验证300/1000/10000lux可读性、延迟与眼盒边缘。

P1固件只实现显示、认证和校时；板载麦克风/RTC的完整离线交互未适配。相机、音频采集和缓存由D0台架负责，没有集成在同一轻量镜架。P1质量、透过率、FOV、功耗和佩戴体验未知，不能套用H1预算。H1光机RFQ、主板/FPC与镜架定版仍须继续。
