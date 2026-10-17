# Android手机端 / v0.2

Android API26+原生Java，编译目标API35。直接官方SDK构建、v2/v3签名校验；API26模拟器已运行TLS配对、任务发送、电脑审批和状态显示。模拟器测试的智能体明确是SIMULATOR，不是Codex模型执行。API35系统镜像本次未达到启动验收。

~~~bash
python scripts/build_android.py --sdk 官方AndroidSDK目录
adb install -r build/android/agentglass-debug.apk
~~~

保留Android Studio/Gradle源码，但本轮执行的是直接SDK构建。调试签名不是生产发行签名；本次复用先前交付的调试签名以维持升级身份。若自行构建出现签名不匹配，不能在未备份媒体时卸载应用。自动测试的--fresh-app只删除本项目临时AVD内的测试应用，不适用于个人设备资料。

## 使用与可靠性

1. 核对电脑完整证书指纹和真实地址后配对。只接受HTTPS，保留主机名验证，不跟随跳转。令牌按证书隔离，Android Keystore AES-GCM保护，禁用系统备份。
2. 选择项目、动作、中文/英文语音或文本；核对后发送。确认绑定当前连接对象，换电脑后必须重新确认。只对未获回复的提交保留重试ID，收到回复后清除。
3. 电脑本地批准后启动。手机展示真实状态/步骤/结果，不计算虚构百分比。completed是智能体回合结束，不是测试正确性证明。
4. D0需系统加密绑定、USB配置密钥。P1 T-Glass V2使用独立地址/密钥，显示连接可与D0并存；与Halo专用协议不兼容。
5. 媒体分块、fsync、SHA-256和原子元数据完成后才确认眼镜删除。恢复支持旧数字ID和新128位base32 ID。重复公告可核验已落盘文件；ID/内容冲突拒绝覆盖。
6. 上传先持久化幂等ID，重试恢复偏移；单个损坏记录被保留并跳过，不阻断其他媒体。最近媒体按接收时间选择，不按上传修改时间。
7. ASR/视觉需明确上传/费用同意，电脑默认关闭；转写不自动执行任务。系统语音识别可能自行联网，不能承诺离线或噪声指标。
8. 手机TTS或有界短语音传眼镜；按唯一utterance回调避免串用旧文件。BLE缓冲播放延迟/音质未验收。
9. 通知默认关闭，仅转发用户选择应用的标题；标题也可能含隐私，不上传正文。

轮询只允许一个在途请求，不积压；控制、取消、接收和上传分别有界。BLE一次一个有应答写入，HUD合并最新值，协商实际MTU。队列满明确拒绝，未确认媒体仍留在眼镜；不能把这些机制称为已经通过弱信号测试。

## 可复现运行检查

~~~bash
python scripts/check_java_audio.py
python scripts/check_java_reliability.py
python scripts/check_android_runtime.py --sdk 官方AndroidSDK目录 --api 26 --boot-timeout 420
~~~

需要官方emulator、platform-tools与AOSP API26 x86_64系统镜像。脚本只针对单独的测试AVD；禁用指标收集。无KVM环境使用软件CPU仿真，可能很慢。真实运行记录包含被安装APK的SHA256；失败记录不改成通过。

当前仍是Activity前台原型，退到后台停止轮询；没有合格的全天后台CompanionDeviceService。没有真机BLE、噪声ASR、音频回环、低延迟、媒体掉电或OTA验收。iOS没有原生应用，网页入口不能代替iOS眼镜媒体/通知支持。
