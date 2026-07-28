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
