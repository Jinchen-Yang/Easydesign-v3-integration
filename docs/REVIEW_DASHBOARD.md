# Stage 5/7 Review Dashboard

Review Dashboard 是 Stage 5/7 的核心 reporting 基础设施。它只读取 RunManifest、
StageManifest 与 bundle 逐级引用且通过 size/SHA-256 校验的 artifact，不扫描目录猜测结果，
也不重新计算科学门槛、Tier、promotion、selection 或总体判词。

## 页面与科学边界

- Stage 5：`实验方案比较`、`全局候选审查`，后者可切换 Pilot/Expansion；候选保留完整
  denominator、missingness、hard/local gate、`score_screen`、`score_expand_structure` 和
  full-target 证据。
- Stage 7：`设计路线比较`、`全局候选审查`、`双模式预测结果`。Review cohort 是 deep
  absolute-gate pass 中按 `score_deep` 降序、`candidate_id` 升序冻结的最多 200 条，并且
  必须属于 seed-101 Top 400；不足时显示真实 `N/200`，绝不补入失败候选。
- 双模式默认各取本模式最高 `ranking_score`，再按 seed、sample index 打破并列。seed 不同
  时显示非 matched-seed 告警；同一候选还可选择已发布的 matched-seed representative。
- target-aligned binder RMSD、binder internal RMSD、target RMSD、hotspot/contact recovery、
  contact Jaccard 和位移是模型中立的描述性证据。只有独立版本化、带 SHA 的 advisory
  comparison profile 才能显示“支持/不支持”，且永远是 `advisory-only`。

浏览器搜索、排序、散点联动和收藏均为 display-only。收藏使用 report data SHA 作为
localStorage scope，只能导出 CSV/JSON，不写回 run，也不形成 approval receipt。

## 不可变 revision 与失败语义

报告分别写到：

```text
results/05-pilot-filtering/review-dashboard/report-0001/
results/07-final-filtering-and-selection/review-dashboard/report-0001/
```

每个阶段维护自己的 `LATEST`。相同 source identity 的成功重建返回原 revision；source
identity 或 presentation override 改变时产生新 revision。失败也发布独立 failure revision，
`LATEST` 不回退旧页面。Reporting failure 不改变科学阶段状态，但 Stage execution 会记录
warning 和可执行的 `report build` next action。

## CLI

```bash
easydesign view PROJECT --run RUN --report auto|target|stage05|stage07
easydesign report build PROJECT --run RUN --report stage05|stage07
easydesign report export PROJECT --run RUN --report stage05|stage07 --output NEW_PATH
easydesign view NEW_PATH
```

`report build --presentation presentation.yaml` 只接受标题、中文标签、指标顺序、置顶卡片和
默认图轴；额外的 threshold/pass/rank 字段会被 schema 拒绝。

服务只绑定 `127.0.0.1`。结构通过不透明 route 提供，每次请求重新验证普通文件、symlink、
size 和 SHA，并支持单一 byte range。服务拒绝非 localhost Host、路径穿越和未知 MIME，
页面使用本地 3Dmol.js，不产生外部网络请求。

## 3Dmol.js provenance

Review Dashboard 固定使用 npm `3dmol@2.5.5` 的 `build/3Dmol-min.js`。代码、BSD-3-Clause
许可、npm integrity、JS SHA-256 与许可 SHA-256 同时写入资产登记和每个 report manifest；
任一身份不一致都会阻止成功发布。
