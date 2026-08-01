# ADR-0005：Stage 04/06 本机与 Suzhou2 受管执行

- 状态：Accepted
- 日期：2026-08-01
- 任务：ENG-030、ENG-031、UX-008、UI-022、VAL-008

## 背景

Stage 04/06 既需要在当前有 GPU 的机器上直接执行，也需要让已授权用户主动
选择 Suzhou2 八卡公共算力。Suzhou2 不是“本机无 GPU”时才出现的 fallback；即使当前机器
有 GPU，用户仍可以主动提交公共队列。把 SSH 参数写入科学 YAML 会污染可复现配置，
而每个控制端直接启动远程 BoltzGen 又会造成 GPU 抢占、队列不一致和断线后无法恢复。

## 决定

1. 将执行位置建模为非科学 `ExecutionTarget`，不改变 Stage plan 和 manifest 契约。
2. “当前机器”保持 `LocalCurrentHostTarget`：由当前工作区直接调用
   `execute_pipeline`，使用工作区本地 GPU lease、心跳和 UI 进度，不经过 Manager 或 SSH。
3. Suzhou2 在 `/data/easydesign/managed-worker` 使用独立私有仓库
   `Knitua/easydesign-managed-worker`，真正拥有中央队列、一卡一租约、恢复和 systemd 服务。
   EasyDesign 主仓库只保留协议、SSH 提交/观察和结果同步。
4. `RemoteJobBundle` schema 0.2 不允许任意 shell，且只接受完整 `(4,5)`、
   `(6,7)`；ProteinDigger 无条件提交这两种范围，筛选在 Suzhou2 原地完成。
5. `ManagedWorkerProbe` schema 0.2 报告 Manager/EasyDesign 版本、两条阶段链、
   BoltzGen/Protenix-v2/TNP、8 GPU、队列和磁盘。版本、schema 或能力不匹配时 fail closed。
6. 每个控制端使用独立 SSH key 与经确认的 host fingerprint；首版 root 只用于授权
   开发者内测，不视为正式多用户安全方案。
7. 远程 Stage 04→05、Stage 06→07 原地连续；同步分 metadata/review/complete 三档，
   默认不回传大型候选。

## 结果

- 同一科学配置可在本机或 Suzhou2 运行，不会产生两套科学实现。
- Suzhou2 将来完整 clone EasyDesign 时使用独立 workspace；它作为“当前机器”客户端仍提交
  同一 Manager，不绕过中央 GPU lease。
- 控制端断线不影响远端任务；worker 和 UI 均从不可变记录恢复。
- 需要运维人员审阅 systemd unit 建议并完成首次安装；EasyDesign 不自动写 `/etc`。
- 未来多用户必须从共享 root 迁移到独立账号或服务身份，队列和 ownership 字段可
  继续复用。

## 被拒绝的方案

- 将 host/password/key 写入每份项目 YAML：泄露机器状态并破坏配置可分享性。
- 控制端通过 SSH 直接启动任意 shell：无法中央防止 GPU 重复占用，安全边界也过宽。
- Stage 04/06 完成后回传全部候选再筛选：在 50k 规模下产生不必要传输和双份存储。
- 无状态多个 SSH worker：无法保证一 GPU 一租约、队列顺序和服务重启恢复。
