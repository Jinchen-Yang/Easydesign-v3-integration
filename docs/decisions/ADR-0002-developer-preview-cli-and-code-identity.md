# ADR-0002：Developer Preview CLI、Runtime Profile 与代码身份

- 状态：`accepted`
- 日期：2026-07-25
- 决策范围：安装入口、CLI/API 边界、本机配置和 RunManifest 代码身份

## 背景

Stage 01/02 已经有真实 Python API 和 APOE smoke，但使用者仍需手工构造 adapter、环境变量
和脚本。继续开发 Stage 03 会扩大“代码已经存在但普通使用者无法稳定调用”的差距。同时，
旧 RunManifest 只接受 Git commit，无法如实描述 dirty checkout 或从 wheel 运行的代码。

## 决策

1. 暂停 Stage 03，先提供 `easydesign` Developer Preview console-script。
2. CLI 只解析参数和展示结果；项目初始化、配置验证、环境诊断、pipeline、run 查询和
   Viewer 均调用可复用 Python API。
3. 用户科学参数只存在于 `easydesign.yaml`；机器路径只存在于一个用户级 runtime
   profile。CLI 不扫描 Conda、权重或系统 Python，也不合并多个 profile。
4. `easydesign run` 只执行当前真实实现的 Stage 01/02。Stage 03–07 在创建 workspace 前
   明确失败，禁止用占位成功推进。
5. RunManifest 1.1 使用结构化 `code_identity`：clean Git commit、dirty package tree
   hash 或 installed package tree hash。旧 1.0 manifest 保持可读。
6. 当前只支持私有源码、editable install、普通本地 install 和本地 wheel；不发布 PyPI，
   不添加公开 LICENSE，也不把 Developer Preview 称为稳定公开 API。
7. 顶层 TODO 除七阶段外统一维护工程、CLI、报告、UI、验证、数据、发布、论文和商业
   workstream；活跃任务必须带已登记 ID。

## 后果

- 使用者可以从真实 target 初始化项目，先验证配置与环境，再用一个命令运行 Stage 01/02。
- 重型 backend 仍需独立安装；`doctor` 只诊断，不负责下载权重或修改环境。
- CLI 本身可跨平台安装，但 Protenix/ScanNet 等 backend 的平台能力必须由 profile 和
  doctor 如实报告。
- dirty checkout 可以用于开发 smoke，但 manifest 会明确记录 dirty 状态和内容哈希。
- resume、结构输入、Stage 03、完整 UI、公开发布和兼容性承诺仍属于后续工作。
