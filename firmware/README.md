# D0 / P1 固件：已交叉编译，未烧录实物

硬件为 ESP32-S3-WROOM-1-N16R8 开发板加外设，具体接线见 `include/pins.h` 和 `hardware/assembly/d0-wiring.csv`。D0 没有 VGA020/透明光机驱动。另提供 P1 TGlass V2 专用近眼显示固件；它与 D0 是分体开发平台，不是 H1 轻量整机。

## 已编写的实际驱动

- ST7789 SPI 240×240初始化、单色128×64手机栅格HUD、简单独立时钟。手机通过认证status消息同步Unix时间和时区；冷启动未校时显示`--:--`，不显示编造的时间。
- OV2640 DVP JPEG采集；物理许可输入必须为高；先本地写入，再公布媒体。短按BOOT可独立拍照。复位/烧录时GPIO0的启动用途仍须遵守。
- 320×240目标5fps短JPEG帧录制，最长15秒；附真实时间戳，实际帧率待测。无需手机即可缓存，但没有完整本地菜单。
- I2S麦克风16kHz PCM16 WAV，最长8秒；MAX98357A提示音与短PCM语音播放。手机TTS文件转为16kHz单声道，先分块缓存于PSRAM、验SHA-256，再播放。当前BLE传输等待较长，**不满足已验证的低延迟语音目标**。
- SD优先、内部SPIFFS回退；不自动格式化失败介质；容量不足拒绝采集，不覆盖未ack媒体。SPIFFS分区约9.94MiB，不能宣传为大容量长期录像。
- BLE加密绑定、USB物理配钥、每次启动随机session、HMAC认证、递增序号、防重放、命令长度和队列限制。

## 构建、配置和烧录

```bash
python -m pip install platformio
python scripts/build_firmware.py
# 明确选择台架目标，确认接线后烧录；下面操作需要真实开发板
PLATFORMIO_SETTING_ENABLE_TELEMETRY=no python -m platformio run -d firmware -e codexglasses_d0 -t upload
python -m platformio device monitor -b 115200
```

确认模块实际为16MB Flash、8MB octal PSRAM。自定义board配置避免把8MB开发板默认值误用到16MB缓存分区。不要改用GPIO35–37，它们属于该PSRAM变体。首次使用内部缓存，需在USB终端按住BOOT后发送`format-cache`再回车；这会擦除内部媒体，应仅用于确认可清空的首次介质。SD应事先在电脑格式化并检查。

生成32字节随机配件密钥，妥善保存；USB按住BOOT，发送`provision `后接64位十六进制密钥并回车。固件不回显密钥。蓝牙配对密码打印到USB终端，Android系统完成加密绑定后，手机再配置相同的HMAC密钥。配钥过程可能被串口工具的输入历史记录保存，应使用受信任工具。

## 当前尚未实现或验证

没有签名OTA、安全启动、Flash加密、Wi-Fi突发媒体协议、双麦波束形成、AEC、离线自然语言ASR、独立唤醒词、接触面温度闭环或H1低功耗状态调度。主循环的2ms轮询和台架背光不满足H1功耗预算。电量保持null，不能用未经标定的ADC值映射为百分比。

缓存flush/rename和手机fsync降低丢失风险，但SPIFFS/SD在掉电、磨损、FAT目录更新及拔卡时仍需故障注入试验。短语音使用有界缓存和简单重采样，不是音质/延迟验收。跨平台BLE连接、PASSKEY交互、真实显示偏移、I2S槽位、扬声器音量和相机时序均待实物验证。

D0只能在离体开发夹具上供电测试。摄像头电源测试板不隔离DVP/SCCB/XCLK的反向供电；完整物理隐私和热安全未通过。

## P1：有实际采购路径的近眼显示

`codexglasses_tglass_v2` 是独立的 ESP32-S3 / TGlass V2 显示目标；`scripts/build_firmware.py` 同时构建 D0 与 P1，并保存两个实际退出码、内存占用和镜像哈希。P1 使用原厂 MIT 驱动的固定版本，源码与许可在 `third_party/lilygo-tglass-v2/`。

```bash
PLATFORMIO_SETTING_ENABLE_TELEMETRY=no python -m platformio run -d firmware -e codexglasses_tglass_v2 -t upload
```

P1 将手机 128×64 位图保留左右边缘后映射到 126×126 显示窗口；支持独立时钟、USB 配钥、加密 BLE 绑定及 HMAC HUD。`photo/record/audio/read` 在此配置明确返回不支持；采集由 D0 或手机承担。Android 可以分别绑定采集板与显示板，两者使用不同密钥。完整采购、显示窗口和 USB BOOT 配钥步骤见 [P1 指南](../hardware/optics/p1-tglass-v2.md)。

v0.2 媒体 ID 为 128 位随机数的 26 字符小写 Base32；`/` + ID + `.jpg` + NUL 共 32 字节，满足当前 SPIFFS 文件名限制，临时文件使用 `.p`。旧版 1–10 位纯数字 ID 仍可读。实际固件头文件经过 256 组跨语言向量和栅格边界测试；这不能证明存储介质掉电安全或 DMA 显示时序。

**P1 和 D0 均只通过编译和主机侧核心测试。没有烧录、真实近眼显示、BLE、相机或音频实测记录。**
