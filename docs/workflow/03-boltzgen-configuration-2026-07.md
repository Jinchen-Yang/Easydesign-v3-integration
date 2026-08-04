# Stage 03 2026-07 历史

## S03-001 / DATA-002：基础 BoltzGen VHH 策略编译器

- 状态：`smoke-validated`
- 完成时间：2026-07-26T01:17:39+08:00
- 实现提交：`15ad37823a38ff543708c35c00c6a0207f022883`

### 完成内容

- 配置升级为 schema 0.7 和 package `0.1.0.dev5`，加入 Stage 03–07 类型化配置边界，
  当前 application 正式执行到 Stage 03。
- 建立 manifest-only Stage 03 continuation：验证并复制终态 Stage 01/02 handoff，
  不改写源 run。
- 实现 `boltzgen-vhh-basic-v1`：每个批准区域与七个官方 VHH scaffold 形成完整笛卡尔
  积，全部区域成员为 positive binding，非 hotspot residue 保持中性。
- 引入 BoltzGen 0.3.2 官方 `official-vhh7-v1`、上游 MIT license、逐文件固定
  SHA-256、wheel package data 和资产登记。
- 实现精确 version/commit/clean-tree/cache probe、有界并发官方 `boltzgen check`、
  逐任务 stdout/stderr、StrategyBundle、矩阵、attempt/Stage/Run manifest。

### 验证证据

- Python 3.11：`make check` 通过；全仓 `189 passed, 8 skipped`。
- `make build`：Viewer/scaffold/license 共 `21/21` 个 wheel asset 字节一致，隔离
  console-script smoke 通过。
- 通用 fixture 覆盖 1/2/3 区域、非 A/B/C ID、不同预算、完整矩阵、target checksum、
  禁止覆盖和禁止 `not_binding`。
- APOE 正式 run：
  `/root/autodl-tmp/Protein_design/easydesign-clean/runs/apoe-s02-006-pse/`
  `20260726-002-stage03-basic-vhh`。
- APOE StrategyBundle 21 个策略，A/B/C × 7 scaffold，每策略预算 40，21/21
  BoltzGen 0.3.2 官方校验通过；bundle SHA-256
  `a8451f5f7f7b7d09e69fbf7cf966c04b70aef01a3863132671b756aa4fe64b87`。
- RunManifest revision 3 为 `succeeded`，`runs show` integrity 为 `verified`。

### 遇到的问题

- 串行官方校验反复初始化，21 份 YAML 耗时过长。
- 首次并发校验把 cache 指到父目录，BoltzGen 无法命中 `mols.zip` 并尝试访问当时不可达
  的 Hugging Face；21 项全部失败。
- 首次正式 continuation run 先把 capability 写进 artifacts，触发编译器“目录必须
  为空”的不可变保护。
- wheel smoke 使用 system-site-packages 时，pip 发现系统中相同开发版本而跳过安装，
  导致临时环境没有 console script。

### 解决办法

- 使用显式 1–8 的有界 worker 并发，但每份 YAML 仍执行独立官方 check、保存独立日志，
  最终按策略顺序汇总。
- `cache_root` 固定指向 Hugging Face cache 本身；默认 `HF_HUB_OFFLINE=1`，probe 验证
  唯一 `mols.zip` 及 SHA-256
  `3d4f56ac4262e745bb3d09cfaa19099b1d01be208122d501667b952e45521e53`。
- 调整 Stage 03 写入顺序为 probe → 空目录编译 → capability/validation；新 run
  使用新 ID，未覆盖失败证据。
- wheel smoke 使用 `pip --force-reinstall`，确保脚本来自正在验证的 wheel。

### 遗留问题

- 基础模板不实现 crop、H_core/H_cluster、CDR 优化、区域融合、自适应预算和多轮策略。
- BoltzGen 0.3.2 不公开可靠生成 seed；manifest 如实写为 unsupported。
- Stage 03 只证明配置可执行，不证明 APOE binder 科学有效。
- 后续工作转入 S04-001/ENG-008；真实 pilot 前必须重新检查 GPU、显存和磁盘，不终止
  服务器现有非 EasyDesign 任务。
