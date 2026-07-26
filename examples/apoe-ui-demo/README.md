# APOE 只读 UI 证据包

本目录保存 APOE PSE 首条真实工程案例的精简、不可变结果投影。它用于让仓库合作者在
自己的机器上查看与服务器一致的 Stage 01–05 工作台，不用于恢复 BoltzGen 任务、重新
筛选或继续运行 Stage 06。

## 包含内容

- Stage 01–05 当前 RunManifest、StageManifest 和所有正式 ArtifactRef。
- Stage 04 的 21 个策略、840 个候选索引、双 GPU 任务表、进度和事件。
- Stage 05 的 21 个策略分层、840 个小规模候选指标、100 个扩展候选指标、
  12 个初步结构筛选通过候选和 10 个 Protenix 完整目标复核结果。
- 12 个初筛候选的 BoltzGen 原始/复折叠结构，以及 10 个候选的 Protenix 结构。
- Stage 01 target、Stage 02 PSE 红/蓝/黄区域和 Stage 03 的 21 个 BoltzGen YAML。

`bundle-manifest.json` 记录 307 个证据文件的路径、大小和 SHA-256；服务启动前会再次验证。
约 970 MB 的 `tasks/`、非正式 `work/`、runtime 和其他后端中间目录没有提交。

## 使用

在仓库根目录安装 UI 依赖并启动：

```bash
python -m pip install -e ".[ui]"
python scripts/serve_ui_evidence_bundle.py examples/apoe-ui-demo --port 8765
```

浏览器打开 `http://127.0.0.1:8765`。如果程序运行在远程 Linux 服务器，在本机执行：

```bash
ssh -L 8765:127.0.0.1:8765 USER@SERVER
```

然后仍打开同一个本地地址。

只验证数据、不启动页面：

```bash
python scripts/build_ui_evidence_bundle.py verify examples/apoe-ui-demo
```

## 科学边界

- 本次运行的软件执行成功到 Stage 05，但科学结论是
  `stopped-no-scale-winner`：12 个候选通过初步结构筛选，10 个进入 Protenix 复核，
  没有候选满足进入 Stage 06 的位姿稳定性门槛。
- Stage 06/07 对本次 APOE 运行仍是“尚未开始”，不得把通用软件能力误读为 APOE 已完成。
- 该结果是工程 smoke 和可审计科学负结果，不是 APOE binder 的实验验证。
- 包内保留原始不可变配置，其中可能出现服务器历史绝对路径；这些路径只是 provenance，
  不会被只读 UI 执行。
