# Local CLI 与 Target Viewer 指南

- CLI/JSON 必须由同一个类型化 `StepCommandResult` 产生；不得解析日志推断下一步。
- 项目平铺七份 Stage YAML；canonical 配置只以 append-only revision 发布，
  `CONFIG_CURRENT` 只追加。
- 只允许顺序执行同一 run 的下一 Stage。已完成配置一致时只读 no-op；漂移时 fail closed。
- Stage 1 decision 和 Stage 2 hotspots 都要显式 approve。SASA/ScanNet 结果保持独立。
- `LocalStepJob` receipt append-only；worker 使用独立 process session。Ctrl-C 只脱离观察，
  drain 只允许 Stage 4/6 安全检查点。
- 长任务无 `--confirm` 时只返回资源计划，不创建 revision、worker、Stage 或 attempt。
- Target Viewer 只读取 manifest 验证后的结构/report/区域 artifact。A/B/C 固定红/蓝/黄；
  页面不得出现编辑、上传、批准或远程提交控件。
- `step view` 只在前台服务用户指定端口；不自动启动、不自动打开浏览器、不常驻。
- CLI 禁止导入 UI、SSH、Manager、Managed Worker 或正式 release 模块。

验证至少覆盖：命令/JSON一致、配置 revision、顺序与漂移拒绝、decision/approval、重任务确认、
worker detach/watch/drain/resume/lost、Viewer 裸结构与 Stage 2 方法切换。
