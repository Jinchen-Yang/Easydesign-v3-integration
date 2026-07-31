---
id: safe-pml
title: 安全 PML
keywords: []
---

始终保留所有 `# @easydesign` 管理行。不得增加、删除或改写这些管理行，也不得用 PML 覆盖 EasyDesign 已加载的 target。
禁止 `run`、`system`、`shell`、`quit`、`reinitialize`、Python 块、文件写入和网络加载。
只引用上下文中真实存在的对象名；新 selection 必须先用 `select` 定义。
优先追加局部、可逆命令，不覆盖用户无关的设置。
输出前检查括号配对，且不得留下 `<object>`、`[selection]` 等占位符。
