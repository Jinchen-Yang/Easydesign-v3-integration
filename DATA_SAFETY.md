# 数据安全与精确删除制度

本文件是 EasyDesign 仓库、开发服务器、计算服务器和数据盘上的最高优先级操作制度。
任何 Coding Agent、自动化脚本或人工维护流程在开始工作前都必须阅读并遵守本文件。
本制度高于任务便利性、磁盘清理需求、同步工具默认行为和其他工程惯例。

## 1. 核心原则

1. **先按价值分类。** 用户输入、`projects/`、科学 `runs/`、manifest、终态 attempt、
   当前或回退 activation 引用的 release、唯一证据、密钥、已发布环境和模型属于受保护
   数据；删除必须取得用户对精确清单的本次批准。
2. **可再生垃圾确认后直接删除。** 仓库生成的开发 cache、bytecode、空占位、失败前尚未
   发布的 build staging，以及已确认无引用的重复构建产物，不得为了回避判断而归档。
   删除前必须证明路径精确、无活动进程、无引用、可再生且不包含受保护数据。
3. **废弃的 Git 内容通过 diff 删除。** 无引用的旧文档、兼容配置、空 `.gitkeep` 和一次性
   工具应从当前树删除；Git 历史就是恢复来源，不再复制到新的 legacy/archive 目录。
4. **删除权限有边界。** “整理”不授权删除受保护数据；用户对某一类可再生目标的明确批准
   也不得扩大到父目录、相邻目录、`.venv/`、`runtime/`、`runs/` 或其他主机。
5. **有疑问就停止。** 路径、挂载点、变量、权限、来源、引用关系或恢复能力有任何不确定
   时，必须保持原状并向用户报告，禁止先操作后解释。

## 2. 删除操作边界

以下操作针对受保护数据时必须逐次批准；针对可再生目标也不得使用宽泛范围：

- `rm`、`rmdir`、`unlink`、`find -delete`、`shutil.rmtree`、`Path.unlink` 等删除操作。
- `git clean`、`git reset --hard`、`git checkout --` 等丢弃工作树或未提交内容的操作。
- 带 `--delete`、`--remove-source-files` 或等效选项的 `rsync`、同步和镜像命令。
- 覆盖已有目标的复制、移动、重命名、解压、安装、重建环境或部署。
- `conda env remove`、包管理器全局清理、Docker prune、日志轮转和运行时目录清理。
- 格式化、重新分区、卸载磁盘、清空回收站、重装系统或重置实例。
- 用空文件覆盖、截断文件、重写历史 manifest、覆盖终态 run/attempt 等逻辑删除。
- 通过脚本、通配符、变量展开、远程命令或第三方工具间接完成上述行为。

**EasyDesign 的同步命令永久禁止使用 `--delete`。** 即使用户批准删除受保护数据，也必须把“同步”
和“删除”拆成两个独立步骤：先完成非破坏性复制与校验，再单独申请删除批准。

允许直接删除的仓库内目标必须同时满足：

1. 使用已解析的精确绝对路径，不含 glob、命令替换、符号链接或父目录递归范围。
2. 删除前记录文件数、字节数、Git ignore/tracked 状态、引用检查和活动进程检查。
3. 目标属于开发 cache、bytecode、空目录/`.gitkeep`、无引用 build，或是本次 Git 变更
   明确淘汰的文档、配置和测试占位。
4. 恢复方式明确：工具可重新生成，或 Git 历史可恢复；否则转为受保护数据审批。
5. 删除后运行结构检查和与风险相称的完整测试，不以删除规避失败的质量门。

## 3. 永远不得作为删除目标的宽泛路径

任何情况下都不得把以下宽泛路径或其变量形式作为递归删除、清空、覆盖或镜像删除目标：

```text
/
/root
/root/autodl-tmp
用户主目录
系统盘根目录
数据盘根目录
工作区根目录
仓库根目录
未解析变量、命令替换或通配符得到的路径
```

禁止依赖 `$HOME`、`~`、空变量、相对路径、`..`、宽泛 glob 或命令替换决定潜在破坏性
目标。即使路径解析正确，也不能绕过第 1 节的用户批准要求。

## 4. 移动、归档与复制

用户允许移动和归档，但必须满足全部条件：

1. 使用精确绝对路径，先只读确认源存在、目标父目录正确且目标不存在。
2. 不使用通配符批量推断范围，不覆盖任何已有目标。
3. 操作前记录源路径、文件数、字节数和关键 manifest/checksum；操作后再次验证。
4. 科学 run 的归档必须遵守 manifest/ArtifactRef 闭包和仓库的可恢复归档规则。
5. 若移动会让其他运行、环境、软链接、服务或远程任务失去引用，必须先停止并报告。
6. 能通过复制到新目录完成时，优先复制并验证；原件继续保留，删除原件另行申请批准。
7. 归档只用于确有独立保留价值且不可由 Git、lock 或构建重现的内容；可再生垃圾不得归档。

## 5. 拉取、部署和跨主机同步

1. 只允许克隆到事先确认不存在的全新目录；目标已存在时立即停止，不覆盖、不合并。
2. 系统盘和数据盘必须先通过只读检查区分；仓库、环境、模型和运行数据优先放在明确的
   数据盘路径。
3. 私有仓库使用独立、最小权限密钥；不得复制或覆盖现有密钥。
4. 跨主机传输只能向全新目录或经过精确校验的目标写入，禁止删除式镜像。
5. 网络、权限或校验失败时保留已存在内容和失败证据，禁止以“重试”为由清空目标。

## 6. 受保护数据删除审批格式

只有在用户明确批准下面这类清单后，才能删除受保护数据：

```text
删除目标：<精确绝对路径列表>
文件数量与大小：<只读统计>
删除原因：<具体原因>
引用检查：<哪些项目、运行或环境引用它>
备份位置与校验：<绝对路径和校验结果；没有则明确写无>
恢复方式：<可恢复 / 不可恢复及原因>
拟执行命令：<完整命令，不含未解析变量和通配符>
```

批准后如果目标、数量、大小、命令或环境发生变化，原批准立即失效，必须重新申请。

## 7. 事故响应

发现误操作风险、异常路径、磁盘内容变化或疑似丢失时：

1. 立即停止所有写入，不执行任何清理、修复、重装或“试探性恢复”。
2. 保存只读证据：挂载信息、时间、命令、日志、目录清单和可用快照信息。
3. 如实报告已经执行和未执行的操作，不把推测写成事实。
4. 恢复方案必须先在副本或新目录验证；原盘保持只读优先。
5. 未经用户批准，不得因事故处理删除临时证据或覆盖残留数据。

## 8. 当前服务器恢复专用约束

在新的 ProteinDigger 实例恢复 EasyDesign 时：

- 只在 `/root/autodl-tmp/Protein_design/easydesign-clean` 不存在时创建并克隆。
- 不触碰 `/root/autodl-tmp` 下任何其他项目、环境、缓存、归档或用户数据。
- 不使用任何带删除语义的同步选项。
- 不清理系统盘或数据盘；磁盘空间问题只做只读审计并单独报告。
- GitHub 拉取完成后先核对 commit、版本、文件数量和仓库状态，再进行任何环境恢复。

## 9. EasyDesign 自包含工作区边界

正常运行以仓库根 `easydesign-workspace.yaml` 为唯一定位依据。仓库内允许写入的顶级
目录固定为：

```text
runtime/
projects/
runs/
archives/
.git/
```

约束如下：

1. `./easydesign` 必须从自身位置解析工作区；不得依赖调用者当前目录、全局 PATH、
   `/root/.config/easydesign` 或其他 home 目录。
2. 用户显式选择的 PSE、PDB、mmCIF、FASTA、A3M、SSH key 等外部文件只允许读取。
   EasyDesign 不得在其父目录创建 cache、sidecar、日志或临时文件。
3. Conda、pip、Node、Corepack、Playwright 和下载器的临时 HOME/cache/tmp 只能由安装
   器作为子进程环境变量传入 `runtime/`；不得写入 shell profile、系统代理、Git 全局
   配置或 base Conda。pip 必须忽略系统/用户配置和 user-site；Git 必须使用工作区内
   仅含 safe-directory 的隔离配置，不得 include 用户全局 Git 配置。
4. 新环境、模型、run 和发布 artifact 必须先写入全新 staging，校验后原子发布到此前
   不存在的目标。目标已存在时拒绝覆盖。
5. 失败 staging、失败下载和临时上传只能移动到
   `runtime/quarantine/<operation-id>/`。系统不自动删除 quarantine、旧环境、旧模型、
   cache 或科学运行。
6. mutable registry/index 必须保存不可变 revision；读取最高合法 revision。损坏的新
   revision 不得覆盖或遮蔽更早的有效记录。
7. SSH 后端只能写入 runtime profile 中明确声明的远程工作区；禁止把“可连接服务器”
   推断成“可向任意远程目录写入”。
8. BoltzGen、Protenix、ScanNet、TNP 等后端只有在环境 lock 与全部必需 asset 的当前
   revision、大小和 SHA-256 均通过后才可暴露给运行层。缺少任一 checkpoint 必须显示
   `awaiting-approval/not-installed`，禁止让后端自行联网补齐。
9. UI 上传先形成持久 `UploadReceipt 0.2`，文件只允许位于
   `runtime/tmp/ui-uploads/`、事务 staging、项目 `inputs/` 或 quarantine。失败创建
   不得留下正式项目或空 DesignSession；成功项目不得保留重复输入副本。
10. 7 天过期仅生成建议，不触发删除。上传暂存清理必须先展示精确相对路径、数量、大小
    和引用状态；未获针对该清单的明确批准时只能隔离或阻止新上传。`projects/`、
    `runs/`、环境、模型、cache 和普通 quarantine 永不属于上传清理接口。

旧部署导入使用显式 `./easydesign workspace import-legacy ...`。导入只复制并校验证据；
原 profile、环境、模型、cache 和 run 全部保留，旧 Conda 环境不得直接搬迁或删除。

## 10. 单一 main Git 制度

EasyDesign 官方开发只允许一个 Git 分支：`main`。

1. 禁止创建 feature、release、hotfix、codex 或其他开发分支，禁止创建新的 Git
   worktree。每个独立、通过质量门的变更直接形成 `main` 上的小型 Conventional
   Commit。
2. 未完成工作不得通过临时分支保存或推送；应留在 `main` 工作树并在 `docs/ROADMAP.md`
   如实记录。不得因此使用 reset、checkout、clean、stash drop 等方式丢弃内容。
3. 发现历史分支或 worktree 时，必须先证明其提交已经进入 `main`，再处理 Git 引用。
   worktree 内的 runtime、环境、缓存、模型、run 或未提交文件均按本制度的数据保护规则
   原样保留；“只允许 main”不构成删除这些目录或数据的授权。
4. GitHub 只推送并核对 `main`。禁止为了传输提交而创建远端临时分支；确需跨机器传输
   时使用 bundle、format-patch 或其他不会创建开发分支的方式。

## 11. 浏览器结构交互与模型密钥

1. 浏览器 PyMOL、Mol* 和模型助手只能通过 manifest 派生 token 读取当前科学结构；
   禁止把浏览器导出的 PML/PSE/PNG 自动提升为 Target Bundle 或覆盖原始科学 artifact。
2. DeepSeek、智谱 GLM 等 provider 的平台 API key 只能由部署者保存到当前仓库
   `runtime/secrets/structure-assistant/platform-provider.yaml`。该文件禁止符号链接，
   在 POSIX 系统必须为 `0600`；不得写入项目配置、run、manifest、普通日志、Git、
   浏览器 localStorage 或返回给前端。普通使用者界面不得提供 provider 或 key 输入。
3. 模型请求禁止包含坐标、MSA、完整序列、外部输入绝对路径或密钥。请求只允许当前
   完整 PML、场景摘要、结构对象/链/格式/SHA-256 metadata、编号说明、当前区域摘要、
   最近十轮对话、匹配的 PML Skills 和用户文字。完整 PML 只描述浏览器可视化场景，
   不能含结构文件字节或机器路径。
4. 模型返回的完整 PML 必须保留所有 `# @easydesign` 管理行，并通过对象、链、括号、
   selection、占位符和系统/文件/网络边界校验。Mol* 仅投影其可靠支持的命令，不得因
   无法投影而拒绝有效 PyMOL PML，也不得反向覆盖当前 PML。
5. 不得提供交互会话删除接口。会话和 PML 每次修改发布新 revision；异常 revision、
   provider 响应和失败证据按仓库安全写入制度保留，禁止自动清理。
6. ChatPyMol 等参考项目只能复制经过来源和许可证审计的能力或静态资产；不得引入其删除
   API、用户主目录写入、可变覆盖式索引或独立科学项目库。

## 12. Suzhou2 受管算力边界

1. 新 worker 的唯一可写根是 `/data/easydesign/managed-worker`。旧
   `/data/easydesign` 环境、历史 run、APOE 50k 和 `/root/Easydesign/Easycontrol`
   均不得移动、覆盖、删除或当作新 worker staging。
2. 控制端每个工作区生成独立 SSH key；私钥只能写入该工作区
   `runtime/secrets/ssh/`，POSIX 权限必须为 `0600`。私钥不得上传 Suzhou2、
   进入科学 YAML、manifest、普通日志或 Git。
   已有完整 key pair 必须复用；检测到只存在私钥或公钥的一半时必须停止，禁止覆盖式
   重建。
3. 首次配对必须显示并明确确认 SSH host fingerprint。fingerprint 变化时
   禁止继续，不得自动接受新主机身份。
4. UI 可以接受一次性 Suzhou2 登录密码来安装工作区公钥，但密码只能从 localhost
   请求写入单次 OpenSSH PTY；不得持久化、进入 argv、环境变量、日志、异常文本、
   registry 或浏览器存储。公钥安装必须幂等，手动安装继续作为回退路径。
5. 逻辑解绑不是删除授权：它只写入新 registry revision 来禁用提交、同步和
   恢复。本地私钥、远端 `authorized_keys` 条目和历史证据全部保留。
6. `RemoteJobBundle` 只能含固定 pipeline 阶段、预算、版本、校验和相对 artifact；
   禁止任意 shell、未验证绝对路径和删除式同步。
7. 运行中默认只回传 metadata，完成默认只回传 review 证据。`complete`
   必须由用户显式请求；不得因为 UI 刷新、observer 重启或 SSH 恢复而隐式下载
   50k 大型结果。
8. worker 不杀死、抢占或重置非 EasyDesign GPU 进程。无可用 GPU 时任务继续排队，
   不将外部占用转换为清理或杀进程授权。
