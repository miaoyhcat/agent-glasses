# 验收证据

这里记录的是**这台电脑上实际跑出来的**构建与验收输出，不是合成的结果。
每个文件由 `scripts/verify.py`、`scripts/record_build_manifest.py` 和各构建脚本写入；
`build-manifest.json` 里是交付二进制的 SHA-256。

## 关于 2026-10 的改名

仓库从 `agent-glass` 系列改名为 `codex-glasses`（显示名 `CodexGlasses`）。
改名会改变源码文件的字节，所以：

- **源码哈希**（`source_inputs`）记录的是改名前的版本，对应当前代码的等价内容，
  但**不能逐字节复核**；
- **已交付二进制**：
  - `codexglasses-debug.apk` 只是文件改名，二进制没变，**哈希仍然有效**
    （`android-runtime.json` 里的 `apk_sha256` 仍能对上）；
  - `codexglasses-0.2.0-py3-none-any.whl` 因为包内路径要跟着改，**重新打过包**，
    哈希与 `build-manifest.json` 里记录的改名前构建不同。

要恢复完整可复核的证据链，需要在作者环境重跑：
`scripts/verify.py` → `scripts/record_build_manifest.py`
（后者需要固件与 Android 构建产物，普通机器上跑不出来）。

这里**不追改历史记录** —— 证据一旦被改写就不成立。沿用旧数字、并在这里说明它对应哪一版，
比把数字改成「看起来对」更诚实。
