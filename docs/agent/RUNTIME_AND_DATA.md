# Runtime 与数据指南

涉及用户项目、run、manifest、attempt、环境、模型、registry、资产或清理时，先完整读取根
`DATA_SAFETY.md`。

- 本产品只写自己的 `runtime/`、`workspace/projects/`、`workspace/runs/` 和 archives。
- 所有路径相对当前 clone 根解析；根由 `easydesign-workspace.yaml` 定位，不允许文档或代码
  固定开发者主机名、数据盘或 clone 绝对路径。
- 所有 backend 和 worker 只在当前 clone 所在主机运行；不存在远程 executor、受管队列、
  主机配对、跨服务器 handoff 或结果回传。
- 全新 clone 可从仓库锁定配方逐组件安装到自己的 `runtime/envs/`、`runtime/models/` 和
  append-only registry；Conda、pip、Git 和下载 cache 必须继续使用隔离 child environment。
- 主 Python 环境 `.venv/` 是唯一顶级环境入口；bootstrap 必须先在 `runtime/tmp/` 构建
  relocatable staging，完整验证后原子发布，已有 `.venv/` 一律拒绝原地修改。
- 全局 uv 只作为固定版本的宿主机工具直接调用；不得复制、升级或删除。bootstrap 必须覆盖
  HOME/XDG/cache/config/tmp 和 managed-Python 路径，确保 uv 产生的全部状态仍属于当前 clone。
- 环境、模型、registry、inventory 和 runtime profile 必须解析到当前 clone 的
  `runtime/`；禁止从同机其他 clone 或外部绝对路径加载环境/模型。
- runtime profile 只能由当前 clone 的安装/激活流程生成；读取时重新校验所有 backend
  路径均位于本 clone，并以环境 lock、inventory、文件 SHA 或 Git revision fail closed。
- 子进程 cache/home/tmp/log 全部指向本产品 runtime，并设置禁止 bytecode 和离线模型策略；
  不得向当前 clone 之外创建 setup、下载、cache、job 或 registry 状态。
- detached 安装的 request/process/result 保持独立证据；`progress.json` 只作为原子替换的运行态
  projection。观察命令和 `Ctrl-C` 不得向 worker 发送停止信号。
- 科学 worker 必须先启用 Linux Landlock 写隔离；只允许本 worktree 的四个可写根以及 CUDA
  所需的 `/dev`、`/proc` 内核接口。Python 可写性探针必须把共享包目录视为只读，使 JIT 产物
  落入本地 `runtime/cache/torch-extensions/`。Landlock 不可用时 fail closed。
- 旧 UI projects/runs 不读取、不索引、不原地继续；外部项目路径一律拒绝。
- `examples/apoe-ui-demo/` 只读、Git 跟踪、checksum 不变，仅用于 manifest/report 回归。
- manifest/artifact/attempt/config revision 追加新文件，pointer 只追加；禁止扫描目录猜最新项。
- 删除前精确确认 Git/代码/receipt/进程引用与可再生性。cache 可删，科学数据和唯一证据不可删。
