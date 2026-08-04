# Stage 05 2026-08 历史

## ENG-031：Stage 04→05 远程数据本地性

- 状态：`implemented`。
- 完成时间：2026-08-01T03:39:51+08:00
- 实现提交：`bede8e13f161987d5ce77658c73121ba0aeac5b5`。

### 完成内容

- 受管 Stage 04 完成后，Stage 05 在 Suzhou2 同一 managed run 根内消费候选，不先回传大量结构。
- 控制端默认只同步 metadata/review，审批通过不可变 handoff 返回 worker。
- 保持 v1.5/v1.6 筛选规则、门槛和 APOE 历史结论不变。

### 验证证据

- 386 个 Python 测试通过，包括 managed source run SHA-256、Stage 范围和原地 continuation 契约。
- Workbench 非视觉回归 60/60 通过。

### 遇到的问题

- 旧 SSH 提交假设每个后续 Stage 都需要再上传一份上游 run，与大型候选数据的本地性相冲突。

### 解决办法

- `RemoteJobBundle` 显式区分已上传闭包与 managed-run 引用，后者必须位于受管 `runs/` 边界内并核对最新 RunManifest SHA-256。

### 遗留问题

- `VAL-008` 仍需真实极小 Stage 04→05 远程连续验收。

## ENG-032：dev35 禁止拆分 Stage 04→05

- 状态：`implemented`；真实连续 smoke 继续归 `VAL-008`。
- 完成时间：2026-08-01T18:06:33+08:00
- 实现提交：以本记录所在 `main` 提交为准。

### 完成内容

- bundle 0.2 只接受 `(4,5)`；控制端不再根据 `stop_after_stage` 把远程范围缩成 `(4,)`。

### 验证证据

- 协议单元测试同时验证单 Stage 与任意 command 字段均被拒绝。

### 遇到的问题

- dev34 仍允许 `stop_after_stage=4` 产生单 Stage bundle，与新决定的原地筛选契约矛盾。

### 解决办法

- 将连续范围同时固定在协议 validator 和控制端 stage-range 计算中。

### 遗留问题

- 完成固定非 APOE Stage 04→05 真实 Manager 运行。
