# EasyDesign Local 运行边界

除本文件外，`runtime/` 均为本 worktree 的 Git 忽略状态。它只保存 Local 产品可写数据，
不保存共享科学环境和模型。

- `profile.yaml[.revisions/]`：runtime link 生成的绝对 backend profile。
- `state/runtime-link.json[.revisions/]`：共享 runtime identity receipt。
- `state/local-jobs/`、`state/local-projects/`：append-only job 与项目/run binding。
- `state/gpu-leases/`：本机 GPU lease revisions。
- `cache/`、`home/`、`tmp/`：本产品子进程的可写隔离区。
- `logs/`、`validation/`、`quarantine/`：日志、真实 smoke 与失败 staging。

`easydesign runtime link /path/to/easydesign-clean/runtime` 只读校验来源的 env/model、registry
和 inventory；不会在来源执行 setup、下载、cache、bytecode 或 job 写入。来源 identity
变化后必须重新显式 link。科学 worker 通过 Linux Landlock 强制执行写隔离；Protenix 等
后端的 JIT/缓存只能落入本 worktree 的 `runtime/cache/`，不能写共享 env/model。

运行时不自动删除任何内容。释放空间前需精确检查 local job、run、receipt 和可再生性；
用户输入、科学 run/manifest、APOE evidence、共享 env/model 不得作为普通 cache 清理。
