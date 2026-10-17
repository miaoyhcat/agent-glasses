# 电脑端

Python 3.11+，aiohttp HTTPS服务，SQLite WAL持久状态；CLI负责本机批准。浏览器工作台是该程序的同源管理界面，不是单独部署的网站。Linux已运行软件测试；Windows/macOS安装、文件ACL、Docker卷和设备连接仍需实机验收。

`agentglass init` 建立私有状态目录、TLS证书和独立operator令牌。Windows初始化使用icacls移除继承权限，失败则停止。手机只得到设备令牌；operator令牌不传至手机、眼镜或URL。

真实模式需要 `runtime_isolation="docker"`，否则任务失败关闭。默认配置不会把手机变成宿主机远程shell。目录授权必须在本机配置；只接受inspect/fix/test三个高层动作。每次启动和继续均需本机批准项目副本及模型服务处理。具体配置和真实验收见 `agent-integration/codex/README.md`。

媒体保存在私有状态目录中，最大单文件64MiB，总预留配额512MiB；没有未经确认的自动清理。需要磁盘回收时由本机操作者先备份并清理已完成媒体/工作副本。不要在服务器运行时直接编辑数据库。

断线后客户端用cursor续读；服务重启将运行中任务标记unknown。unknown不是失败后可无脑重试的安全许可，必须先检查真实worker和会话，避免重复模型费用、重复修改或错误合并。当前没有后台恢复活动turn的自动编排。
