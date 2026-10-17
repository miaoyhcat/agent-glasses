# 发布到GitHub

仓库采用根目录的个人非商业许可证；公开源码时保留LICENSE、NOTICE.md和COMMERCIAL-LICENSE.md。商业联系3277681859@qq.com。

## 从单文件发布包还原Git仓库

解压发布包后，得到可浏览的`agent-glasses/`目录及`agent-glasses.git.bundle`。若需要保留发布提交和标签，在解压目录执行：

```bash
git clone ./agent-glasses.git.bundle ./agent-glasses-git
cd agent-glasses-git
git bundle verify ../agent-glasses.git.bundle
git log -1 --oneline
```

`agent-glasses/`为同一提交的普通文件副本，适合直接阅读和打开CAD；`agent-glasses-git/`为离线克隆生成的Git工作区，两者无需同时修改。

## 推送公开仓库

1. 在[GitHub新建仓库](https://github.com/new)，名称可用`agent-glasses`，选择Public并创建空仓库，使用本项目已有README与LICENSE。
2. 将以下`YOUR_ACCOUNT`替换成拥有该仓库权限的账户，在上述Git工作区执行：

```bash
git remote add origin https://github.com/YOUR_ACCOUNT/agent-glasses.git
git push -u origin main
git push origin --tags
```

若已有origin，先用`git remote -v`核对目标，不盲目替换已有远端。认证使用用户自己的GitHub标准认证方式，不把令牌写入仓库或命令示例。

## 发布页核对

首页应显示中文介绍、显著的个人自用/商业授权政策、产品对比和设计资料索引。检查LICENSE、NOTICE.md、源文件及安装包均可访问。硬件设计参数、厂商规格和测试记录在原资料中分别标注，发布说明沿用这些口径。
