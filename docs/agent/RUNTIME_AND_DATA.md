# Runtime 与数据指南

涉及用户项目、run、manifest、attempt、环境、模型、registry、资产或清理时，先完整读取根
`DATA_SAFETY.md`。

- 本产品只写自己的 `runtime/`、`workspace/projects/`、`workspace/runs/` 和 archives。
- 原 `easydesign-clean/runtime` 仅可通过 runtime-link receipt 读取 `envs/`、`models/`、两个
  registry marker、append-only revisions 和 environment inventories。
- link 时验证本分支环境 lock、registry tip/revision SHA、inventory SHA、文件 size/SHA 或
  Git revision；任一 identity 改变即 fail closed，要求重新 link。
- 子进程 cache/home/tmp/log 全部指向本产品 runtime，并设置禁止 bytecode 和离线模型策略；
  来源 runtime 禁止 setup、下载、cache、job 或 registry 写入。
- 科学 worker 必须先启用 Linux Landlock 写隔离；只允许本 worktree 的四个可写根以及 CUDA
  所需的 `/dev`、`/proc` 内核接口。Python 可写性探针必须把共享包目录视为只读，使 JIT 产物
  落入本地 `runtime/cache/torch-extensions/`。Landlock 不可用时 fail closed。
- 旧 UI projects/runs 不读取、不索引、不原地继续；外部项目路径一律拒绝。
- `examples/apoe-ui-demo/` 只读、Git 跟踪、checksum 不变，仅用于 manifest/report 回归。
- manifest/artifact/attempt/config revision 追加新文件，pointer 只追加；禁止扫描目录猜最新项。
- 删除前精确确认 Git/代码/receipt/进程引用与可再生性。cache 可删，科学数据和唯一证据不可删。
