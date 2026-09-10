# EasyDesign Agent：Phase 1

`easydesign-agent` 直接调用模型 API，协调 Target Intelligence 和只读 Evidence Judge，
并复用原来的 target preparation、manifest、DecisionRequest/Record 和 local worker。
v2 的 `easydesign` 命令继续可用。此 migration 分支只支持本地 PDB/mmCIF、review-gated、
stop-after-target 项目；不进行远端身份检索、结构预测、site/binder 设计或 Stage 02–07。

## 安装 optional agent 环境

先按主 README 完成当前 clone 的基础安装。不要在已发布的 v2 环境中原地添加依赖。
在当前 clone 根目录，使用全局 `uv 0.12.3` 创建一份新环境；下面的目标必须不存在。
已有目标时保留它，选择新的独立 staging/发布名称。

```bash
(
set -eu
mkdir -p runtime/tmp runtime/cache/uv runtime/home/agent-install runtime/envs
export UV_CACHE_DIR="$PWD/runtime/cache/uv"
export UV_PYTHON_INSTALL_DIR="$PWD/runtime/tools/uv-python"
export UV_NO_CONFIG=1
export XDG_CONFIG_HOME="$PWD/runtime/home/agent-install"
export TMPDIR="$PWD/runtime/tmp"
test ! -e runtime/tmp/agent-phase1-staging
test ! -e runtime/envs/agent-phase1
uv venv --relocatable --python .venv/bin/python runtime/tmp/agent-phase1-staging
UV_PROJECT_ENVIRONMENT="$PWD/runtime/tmp/agent-phase1-staging" \
  uv sync --locked --extra agent --extra dev --python .venv/bin/python
runtime/tmp/agent-phase1-staging/bin/python -c 'import easydesign.agent.harness'
mv -n runtime/tmp/agent-phase1-staging runtime/envs/agent-phase1
)
source runtime/envs/agent-phase1/bin/activate
easydesign-agent --help
```

依赖版本与传递依赖由 `uv.lock` 固定；科学 backend 的独立环境与模型不变。
安装失败保留诊断和 staging，不覆盖已发布环境。wheel 安装也包含两份专家 SKILL.md。

## 配置一个可用模型

首次安装且 `config/llm.yaml` 不存在时，复制标准模板。已有文件保留并直接编辑，不覆盖：

```bash
cp -n config/llm.template.yaml config/llm.yaml
```

模板使用 DeepSeek 官方 API 的 `deepseek-flash`，对应 2026-09-10 官方文档的 V4.1 Flash。
模型别名由 provider 管理，执行记录与配置一起保留；不能把别名当作不可变权重版本。
参见 [DeepSeek 官方 API 文档](https://api-docs.deepseek.com/)。设置密钥：

```bash
export DEEPSEEK_API_KEY="<YOUR_KEY>"
```

如需长期保存本机变量，可从 `.env.example` 创建私有文件：

```bash
cp -n .env.example .env.local
chmod 600 .env.local
# 使用编辑器将 .env.local 中的占位符替换为真实 key。
```

程序不会自动读取 `.env.local`。启动前在可信的本地 shell 加载：

```bash
set -a
source .env.local
set +a
```

不要将真实 key 提交到 Git。`.env.local` 和 `config/llm.yaml` 已列入忽略规则。
模型配置只记录环境变量名，不记录变量值；Agent state、checkpoint、日志和科学 worker
不接收模型密钥。远程 tracing 默认关闭，不需要 LangSmith 服务。

Phase 1 支持 `deepseek`、`openai`、`anthropic`。切换 provider 时必须同时修改模型名和
密钥变量名，不能只改环境变量。例如使用账户已开通的模型：

```yaml
default:
  provider: openai
  model: YOUR_ENABLED_OPENAI_MODEL
  secret_env: OPENAI_API_KEY
  timeout_seconds: 90
  max_output_tokens: 2048
roles: {}
max_model_calls: 32
max_input_chars: 60000
```

Anthropic 则设 `provider: anthropic`、该账户可用的模型名与 `ANTHROPIC_API_KEY`。
可在 `roles` 下对 `coordinator`、`target`、`judge` 单独覆盖同样的配置。
Phase 1 不实现 OAuth、OpenRouter、Gemini 或用户自定义 endpoint；未知字段明确拒绝。
DeepSeek 使用官方固定 endpoint 和非 thinking 工具调用，避免未验证的 reasoning 消息回传。

## 运行与恢复

为新项目选择一个小型本地双链结构。CLI 的问题应包含研究者真正想准备的链；没有偏好时
Agent 应先澄清。输入文件只读，项目由旧初始化入口冻结输入。

```bash
easydesign-agent start my-target \
  --target /absolute/path/to/two-chain.pdb \
  --goal '准备这份本地结构中的链 A；显示证据和局限，等待我确认。'
```

终端输出 `thread` 与决定卡。关闭进程后可以恢复同一个 thread：

```bash
easydesign-agent resume my-target --thread THREAD_ID
easydesign-agent resume my-target --thread THREAD_ID --card CARD_ID --decision approve
# 或 --decision reject；拒绝保留原科学请求，不生成批准 record。
```

也可加 `--interactive` 在本地终端输入 approve/reject。`approved_by` 来自操作系统用户，
模型不能提供。只支持 approve/reject；选择变化需要重新评估并产生新卡。
拒绝当前卡后，使用 `resume --thread THREAD_ID --message '改为准备链 B，请重新评估'`
提出新选择；审批仍使用新卡，旧响应不会批准新动作。`--stream` 将受限进度事件输出到 stderr。
`status` 只读会话事件，并通过原控制器观察已绑定 job：

```bash
easydesign-agent status my-target --thread THREAD_ID
```

同一项目只使用一个写入口。旧 CLI 不遵守新 Agent 锁，因此不支持与 Agent 并发写入。
配置、证据或请求发生漂移时停止。`reconciliation-required` 表示无法证明提交身份，
请检查报告中的旧 receipt，不能靠再次调用 prepare 重跑。Ctrl-C 只脱离 Agent 观察，
不会停止真实科学 worker。Agent replay、科学 run/attempt 和真实 compute recovery 各自独立。

## 验证和停止

```bash
python -m pytest tests/unit/agent tests/integration/test_agent_target_vertical_slice.py
```

默认测试使用脚本化模型、真实 LangGraph saver 和真实 CPU Stage 01/worker。
真实模型 smoke 必须显式配置凭据并启用：

```bash
EASYDESIGN_AGENT_LIVE=1 EASYDESIGN_AGENT_MODEL_CONFIG="$PWD/config/llm.yaml" \
  python -m pytest tests/integration/test_agent_target_vertical_slice.py -k live -s
```

该 smoke 只使用合成双链结构和独立测试 workspace；测试代码模拟该 fixture 的人工确认，
不代表批准任何真实研究项目。模型调用上限跨进程持久化，SDK 重试关闭，每次输出 token
受限；默认总调用数 32。金额随 provider 当前定价及输入 token 变化，并非固定费用承诺。
没有凭据时 live smoke 跳过并明确报告，不能据此宣布真实模型闭环通过。

成功结果仍明确显示：canonical biological identity 未确认、reference completeness 未知，
结构质量不等于亲和力或功能证据。Viewer 验证失败单独报告，不改变科学成功状态。
Phase 1 完成后停止；不会自动启动后续迁移阶段。
