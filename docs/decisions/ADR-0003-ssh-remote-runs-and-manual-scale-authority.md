# ADR-0003：SSH 远程 Run 与人工规模化授权

- 状态：`accepted`
- 日期：2026-07-27
- 决策范围：跨主机执行、Stage 06 授权、科学停止边界和恢复身份

## 背景

Stage 04–06 已有一套 manifest 驱动的本地多 GPU 执行器，但计算资源不一定与
EasyDesign 控制端位于同一台机器。APOE 同时出现了另一种真实需求：Stage 05 已发布
`stopped-no-scale-winner`，研究负责人仍希望把唯一已扩展 Tier A 做一次明确属于探索性
的 50,000-candidate 生成。直接手工复制 YAML 并后台运行会丢失上游身份、授权、分片恢复
和科学停止记录。

## 决策

1. SSH 是整个 EasyDesign run 的 deployment control plane，不是第二套 Stage 04/06
   科学执行器。远端 worker 仍调用相同 `local-multi-gpu` API。
2. 远端机器只在用户级 runtime profile 中登记。主机、端口、独立 identity、known-hosts、
   work/runs root、EasyDesign executable 和远端 profile 都必须显式声明。
3. 控制端提交前验证本地凭据、远端 EasyDesign 精确版本、GPU/磁盘和 succeeded source
   RunManifest；随后复制完整 continuation source 与配置，并用 systemd 启动持久 worker。
4. 远端 run 独立发布 RunManifest、StageManifest、progress、events 和 task attempt。
   SSH 断开不影响运行；resume 以远端 run 为事实来源。
5. Stage 05 正常 `winner-selected` 仍使用确定性授权。只有
   `stopped-no-scale-winner` 可以声明人工探索性 override，而且 strategy 必须属于
   Stage 05 已扩展 Tier A。
6. 人工授权必须包含授权人、理由、源 Stage05Bundle SHA-256，并明确确认
   `scientific-stop` 仍成立以及该策略并未科学合格。授权作为 Stage 06 正式 artifact
   进入 ScalePlan/ScaleBundle。
7. `stopped-no-tier-a` 永远不能通过该机制越过；Stage 05 历史 manifest 和阈值也不得
   修改。

## 后果

- 计算可以安全提交到另一台 8-GPU 服务器，并保留相同的分片、进度、事件和恢复语义。
- 控制端不需要常驻 SSH 会话，也不会把密钥写进科学配置或 run artifact。
- 一个探索性 50k 运行可以在工程上成功，但它不能被称作 Stage 05 科学通过、最终候选包
  或可下单结果；Stage 07 是否继续仍需另行配置和证据审查。
- 首版使用 rsync、OpenSSH 和 systemd；Slurm/SMART 是后续 adapter，不通过本 ADR
  伪装成已经支持。
