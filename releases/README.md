# 工程调试包 / v0.2

`codexglasses-debug.apk` 为实际 Android 源码经官方 SDK35/JDK17 构建的 v0.2.0 调试包，最低 Android8/API26。已经过 APK v2/v3 签名检查，以及官方 API26 模拟器的安装、TLS 配对、任务提交、本机批准和状态回传七项运行检查。实际 APK SHA-256 与 `docs/evidence/android-runtime.json` 一致；智能体明确是 SIMULATOR。没有实机 BLE、音频、相机或后台稳定性验收。

```bash
adb install -r releases/codexglasses-debug.apk
python -m pip install releases/codexglasses-0.2.0-py3-none-any.whl
```

APK 使用先前交付包的同一工程调试签名；调试私钥不打包。自行重建会产生自己的签名，不能保证覆盖安装。签名不一致时 Android 应拒绝更新；先妥善导出媒体及配置，不能为解决安装错误自动卸载含个人数据的应用。不要把签名有效当作安全认证或正式发布身份。

Wheel 包含当前电脑端源码和工作台。依赖由 pip 另行取得；也可以从仓库根目录 `pip install -e .`。两文件的哈希、构建输入和构建日志见 `docs/evidence/build-manifest.json`（路径相对仓库根目录）。

D0、P1 两固件已交叉编译，但第三方链接二进制再分发义务尚未逐项完成，因此交付源代码、固定依赖和构建记录，供个人自行构建，不分发固件镜像。原创内容遵守根目录个人非商业许可证；第三方条款见 NOTICE.md。全部属于工程预览。
