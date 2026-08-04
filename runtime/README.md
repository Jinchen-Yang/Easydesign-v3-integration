# EasyDesign 本机运行边界

`runtime/` 是当前 EasyDesign clone 的本机部署边界。除本文件外，其内容均不进入
Git，也不得被脚本自动删除。

- `profile.yaml`：仓库相对路径和环境/资产 ID。
- `envs/`：按 lock SHA 隔离的 Conda 环境。
- `models/`：校验后发布的模型与运行资产。
- `cache/`：仅供当前工作区使用的下载和计算缓存。
- `state/`：版本化注册表、UI job 和远程任务状态。
- `logs/`、`tmp/`：运行日志和 staging。
- `quarantine/`：失败 staging、旧草稿和待人工处理内容。
- `secrets/`：本机秘密材料；Git 永远忽略。

EasyDesign 不会自动清理这里的任何内容。需要释放空间时，必须由用户针对精确路径
另行批准。

## 安装与迁移原则

Conda 环境会记录创建时的绝对 prefix，因此旧工作区中的环境不得直接复制后冒充为
当前工作区环境。迁移时只把旧环境和缓存作为只读证据与下载加速来源，在当前
`runtime/envs/` 中根据锁文件重新创建，并通过版本、依赖和后端探针后登记为可用。
旧环境、旧缓存和失败 staging 均保留；失败内容只进入 `runtime/quarantine/`。

在首次安装前可以安全查看单组件计划。`--plan` 不创建环境、缓存或注册记录：

```bash
./easydesign setup --component core-ui --plan
./easydesign setup --component protenix-v2 --plan
```

网络受限时可以为本次安装显式提供经过确认的 HTTPS Python 包索引。该设置只传给
EasyDesign 的安装子进程，不修改系统代理、Git 全局配置、shell profile 或 base
Conda：

```bash
./easydesign setup \
  --component core-ui \
  --pip-index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

长时安装任务位于 `state/setup-jobs/<job-id>/`，日志位于 `logs/`。关闭 SSH 或 UI
不会终止通过 `./easydesign setup --detach` 启动的 worker；状态由不可变 request、
process 和 result 记录恢复，不依赖终端文本。

## 平台结构助手 API

普通使用者不选择模型提供方，也不填写 API key。EasyDesign 部署者只需在当前 clone
创建以下本机文件：

```text
runtime/secrets/structure-assistant/platform-provider.yaml
```

可以从
`config/assistant-provider.example.yaml` 复制字段结构，当前支持
`provider: deepseek` 或 `provider: zhipu-glm`。该文件不得提交 Git、不得使用符号
链接，在 Linux/macOS 上必须设置为仅文件所有者可读写：

```bash
chmod 600 runtime/secrets/structure-assistant/platform-provider.yaml
```

服务端只加载这一份平台配置，不在 provider 之间静默 fallback。前端只能读取
“EasyDesign 结构助手”是否可用，不能读取 provider、模型、endpoint 或密钥。模型请求
仍只发送用户文字、阶段、链、编号体系和当前区域数量，不发送结构坐标、MSA 或完整
序列。
