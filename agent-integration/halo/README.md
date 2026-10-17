# 可选 Halo HUD 平台实验

此适配在完整Halo硬件上尝试显示电脑状态，帮助先验证近眼文字布局；不是H1硬件实现，也不覆盖H1的离线录像或制造要求。

官方Python资料介绍BrilliantBle。本次实际安装并检查公开发行包 **brilliant-ble 3.4.0** 的类和方法签名；网页列出的2.0.0没有在当前包索引提供，因此未把不可安装版本写进依赖。没有连接实物。

```bash
python -m pip install -e '.[halo]'
python agent-integration/halo/hud_relay.py --desktop https://电脑私网IP:9443 --certificate <server.pem> --token-file <低权限设备令牌文件> --name 'Halo AB'
```

须按厂商流程配对，指定准确`Halo XX`设备名，主动断开其他应用占用。只使用设备令牌，不使用operator令牌。Lua命令由固定绘图模板生成，文字用十进制字节转义，不能把项目名变成Lua代码。默认字体不保证中文覆盖；此入口显示英文状态，Android D0位图路线负责中文栅格化。

该脚本会清除当前Halo显示内容，连接期间需停用厂商应用对同一设备的控制。未自动安装应用、重置设备、删除文件或改厂商固件。MTU不足会报错，不假装命令已显示。
