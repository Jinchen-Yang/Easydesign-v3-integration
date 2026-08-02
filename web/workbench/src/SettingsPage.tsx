import { useEffect, useMemo, useState } from "react";

import { api } from "./api";
import type {
  ExecutionTargets,
  InstallStatus,
  ProjectCatalogEntry,
  RemoteExecutor,
  RuntimeInstallItem,
} from "./types";

type SettingsSection = "local" | "compute" | "archive";
type ComponentState = "available" | "running" | "awaiting-approval" | "missing" | "failed" | "unsupported";

const READY_STATES = new Set(["available", "succeeded"]);
const COMPONENTS = [
  {
    id: "core-ui",
    name: "EasyDesign 基础环境",
    description: "启动命令、科研工作台与离线网页资源。",
    group: "required",
  },
  {
    id: "pymol-pse",
    name: "PyMOL / PSE",
    description: "读取 PSE 输入并保留来源颜色。",
    group: "workflow",
  },
  {
    id: "protenix-v2",
    name: "Protenix-v2",
    description: "由序列预测结构，并执行完整目标复核。",
    group: "workflow",
  },
  {
    id: "scannet-epitope",
    name: "ScanNet",
    description: "在第2步生成独立的表位候选区域。",
    group: "workflow",
  },
  {
    id: "boltzgen",
    name: "BoltzGen",
    description: "执行第4步小规模生成与第6步规模化生成。",
    group: "workflow",
  },
  {
    id: "tnp",
    name: "TNP",
    description: "为第7步最终候选补充纳米抗体结构证据。",
    group: "workflow",
  },
] as const;

const STATUS_LABELS: Record<ComponentState, string> = {
  available: "可用",
  running: "安装中",
  "awaiting-approval": "等待许可确认",
  missing: "未安装",
  failed: "需要处理",
  unsupported: "当前平台不可用",
};

function humanBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  return `${(value / 1024 ** 3).toFixed(1)} GiB`;
}

function formatTime(value?: string) {
  if (!value) return "尚未记录";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function deriveComponentState(
  status: InstallStatus | undefined,
  componentId: string,
  acceptedLicenses: string[],
): { state: ComponentState; approvals: RuntimeInstallItem[] } {
  if (!status) return { state: "missing", approvals: [] };
  const plan = status.component_plans[componentId];
  if (!plan) return { state: "unsupported", approvals: [] };
  const environmentById = new Map(
    status.environments.map((item) => [item.environment_id || "", item]),
  );
  const assetById = new Map(status.assets.map((item) => [item.asset_id || "", item]));
  const environments = plan.environments.map((item) => environmentById.get(item.environment_id));
  const assets = plan.assets.map((item) => assetById.get(item.asset_id));
  const records = [...environments, ...assets].filter(Boolean) as RuntimeInstallItem[];
  const approvals = assets.filter(
    (item): item is RuntimeInstallItem => Boolean(
      item
      && item.license_confirmation_required
      && !READY_STATES.has(item.status)
      && !acceptedLicenses.includes(item.asset_id || ""),
    ),
  );
  if (records.some((item) => item.status === "running")) return { state: "running", approvals };
  if (records.some((item) => item.status === "unsupported-platform")) return { state: "unsupported", approvals };
  if (records.some((item) => ["failed", "incomplete", "interrupted", "outdated"].includes(item.status))) {
    return { state: "failed", approvals };
  }
  if (approvals.length) return { state: "awaiting-approval", approvals };
  if (records.length > 0 && records.every((item) => READY_STATES.has(item.status))) {
    return { state: "available", approvals };
  }
  return { state: "missing", approvals };
}

function Suzhou2Settings() {
  const [executor, setExecutor] = useState<RemoteExecutor>();
  const [targets, setTargets] = useState<ExecutionTargets>();
  const [host, setHost] = useState("");
  const [port, setPort] = useState(22);
  const [user, setUser] = useState("root");
  const [controllerId, setControllerId] = useState("controller-primary");
  const [hostFingerprint, setHostFingerprint] = useState("");
  const [fingerprintConfirmed, setFingerprintConfirmed] = useState(false);
  const [publicKey, setPublicKey] = useState("");
  const [installCommand, setInstallCommand] = useState("");
  const [bootstrapPassword, setBootstrapPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const [executorsResult, targetsResult] = await Promise.allSettled([
      api.remoteExecutors(),
      api.executionTargets(),
    ]);
    if (executorsResult.status === "fulfilled") {
      const current = executorsResult.value.executors.find((item) => item.executor_id === "suzhou2");
      setExecutor(current);
      if (current?.host) setHost(current.host);
      if (current?.port) setPort(current.port);
      if (current?.user) setUser(current.user);
      if (current?.controller_id) setControllerId(current.controller_id);
      if (current?.host_fingerprint) setHostFingerprint(current.host_fingerprint);
    }
    if (targetsResult.status === "fulfilled") setTargets(targetsResult.value);
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function scan() {
    if (!host.trim()) return;
    setBusy(true);
    setMessage("正在读取 Suzhou2 的 SSH 主机指纹…");
    try {
      const identity = await api.scanRemoteHost(host.trim(), port);
      setHostFingerprint(String(identity.fingerprint || ""));
      setFingerprintConfirmed(false);
      setMessage("请通过 Suzhou2 控制台或管理员核对服务器身份指纹，确认后再生成当前工作区的登录密钥。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法读取服务器指纹");
    } finally {
      setBusy(false);
    }
  }

  async function beginPairing() {
    if (!hostFingerprint || !fingerprintConfirmed) return;
    setBusy(true);
    setMessage("正在当前 EasyDesign 工作区生成专用 SSH 密钥…");
    try {
      const result = await api.beginRemotePairing({
        executor_id: "suzhou2",
        controller_id: controllerId.trim(),
        host: host.trim(),
        port,
        user: user.trim(),
        confirmed_host_fingerprint: hostFingerprint,
      });
      const pairing = result.pairing as Record<string, unknown>;
      setPublicKey(String(pairing.public_key || ""));
      setInstallCommand(String(result.public_key_install_command || ""));
      setMessage(result.key_pair_reused ? "已检测并复用当前工作区的专用 SSH 密钥。" : "已在当前工作区生成专用 SSH 密钥。");
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法开始 SSH 配对");
    } finally {
      setBusy(false);
    }
  }

  async function bootstrapPairing() {
    if (!bootstrapPassword) return;
    setBusy(true);
    setMessage("正在使用一次性密码安装公钥并验证 Suzhou2…");
    try {
      const result = await api.bootstrapRemotePairing("suzhou2", bootstrapPassword);
      if (result.status === "paired") {
        const probe = result.probe as Record<string, unknown>;
        setMessage(`Suzhou2 已连接：${String(probe.gpu_count || 0)} 张 GPU 可被统一队列管理。`);
        setPublicKey("");
        setInstallCommand("");
      } else {
        setMessage(`公钥已经安装，但远端 EasyDesign worker 尚未就绪：${String(result.probe_error || "请部署 worker 后重新验证连接")}`);
      }
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "一次性密码安装失败");
    } finally {
      setBootstrapPassword("");
      setBusy(false);
    }
  }

  async function confirmPairing() {
    setBusy(true);
    setMessage("正在验证连接、统一队列、GPU、磁盘和运行环境…");
    try {
      const result = await api.confirmRemotePairing("suzhou2");
      const probe = result.probe as Record<string, unknown>;
      setMessage(`Suzhou2 已连接：${String(probe.gpu_count || 0)} 张 GPU 可被统一队列管理。`);
      setPublicKey("");
      setInstallCommand("");
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Suzhou2 验证失败");
    } finally {
      setBusy(false);
    }
  }

  async function unpair() {
    if (!window.confirm(
      "确认解除 Suzhou2 绑定并返回重新配置？历史运行记录、工作区专用密钥和远端公钥都会保留；重新连接时会安全复用。",
    )) return;
    setBusy(true);
    try {
      await api.unpairRemoteExecutor("suzhou2");
      setFingerprintConfirmed(false);
      setPublicKey("");
      setInstallCommand("");
      setMessage("已解除绑定，可以重新核对服务器并配置连接；历史证据和专用密钥均未删除。");
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "取消连接失败");
    } finally {
      setBusy(false);
    }
  }

  const paired = executor?.pairing_state === "paired";
  const awaiting = executor?.pairing_state === "awaiting-public-key";
  const managed = targets?.managed.find((item) => item.executor_id === "suzhou2");

  return (
    <div className="settings-section-stack">
      <section className={`panel compute-summary ${paired ? "available" : ""}`}>
        <div>
          <p className="section-label">公共算力</p>
          <h2>{paired ? "Suzhou2 已连接" : "Suzhou2 尚未连接"}</h2>
          <p>{paired ? "可在第4步和第6步选择 Suzhou2，并在本工作台跟踪队列和进度。" : "有 Suzhou2 访问权限的使用者可在此完成一次 SSH 配对。"}</p>
        </div>
        <div className="compute-facts">
          <span><strong>{managed ? managed.pairing_state === "paired" ? "可提交" : "未就绪" : paired ? "已配对" : "未配对"}</strong><small>连接状态</small></span>
          <span><strong>{executor?.controller_id || "—"}</strong><small>当前控制端</small></span>
        </div>
      </section>
      <section className="panel suzhou-pairing-settings">
        <div className="panel-heading">
          <div><p className="section-label">连接设置</p><h3>Suzhou2</h3></div>
          <span data-state={executor?.pairing_state || "not-paired"}>{paired ? "已配对" : awaiting ? "等待一次性密码" : "尚未配对"}</span>
        </div>
        <p className="pairing-explanation">先核对服务器身份，再检测或生成当前工作区专用密钥，最后用一次性登录密码安装公钥。已有完整密钥会自动复用，不会读取、替换或修改 ~/.ssh 中的个人密钥。</p>
        {!paired && <>
          <div className="pairing-fields">
            <label><span>服务器地址</span><input value={host} disabled={busy} onChange={(event) => setHost(event.target.value)} placeholder="Suzhou2 主机名或 IP" /></label>
            <label><span>SSH 端口</span><input type="number" min="1" max="65535" value={port} disabled={busy} onChange={(event) => setPort(Number(event.target.value))} /></label>
            <label><span>用户名</span><input value={user} disabled={busy} onChange={(event) => setUser(event.target.value)} /></label>
            <label><span>控制端名称</span><input value={controllerId} disabled={busy} onChange={(event) => setControllerId(event.target.value.trim().toLowerCase().replace(/[^a-z0-9._-]+/g, "-"))} /></label>
          </div>
          <div className="pairing-actions">
            <button type="button" disabled={busy || !host.trim()} onClick={() => void scan()}>1. 核对服务器身份</button>
            <button type="button" disabled={busy || awaiting || !hostFingerprint || !fingerprintConfirmed} onClick={() => void beginPairing()}>{awaiting ? "2. 工作区密钥已就绪" : "2. 检测或生成工作区密钥"}</button>
            <button type="button" className="primary-button" disabled={busy || !awaiting || !bootstrapPassword} onClick={() => void bootstrapPairing()}>3. 用一次性密码安装并连接</button>
          </div>
        </>}
        {hostFingerprint && !paired && <label className="fingerprint-confirmation">
          <input type="checkbox" checked={fingerprintConfirmed} onChange={(event) => setFingerprintConfirmed(event.target.checked)} />
          <span><strong>我已通过 Suzhou2 控制台或管理员核对服务器身份指纹</strong><code>{hostFingerprint}</code></span>
        </label>}
        {awaiting && <div className="pairing-password-box">
          <label>
            <span>Suzhou2 一次性登录密码</span>
            <input
              type="password"
              autoComplete="current-password"
              value={bootstrapPassword}
              disabled={busy}
              onChange={(event) => setBootstrapPassword(event.target.value)}
              aria-label="Suzhou2 一次性登录密码"
            />
          </label>
          <small>密码只发送到本机 127.0.0.1 的 EasyDesign 服务，并仅用于本次 SSH 认证；不会保存、写入日志、命令参数或环境变量。</small>
          {executor?.key_pair_available && <strong>已检测到完整的工作区专用密钥，本次会直接复用，不会重新生成。</strong>}
          <button type="button" disabled={busy} onClick={() => void confirmPairing()}>公钥已手动安装，直接验证</button>
        </div>}
        {(publicKey || installCommand) && <div className="pairing-key-box">
          <strong>在 Suzhou2 安装这把 EasyDesign 登录公钥</strong>
          {publicKey && <textarea readOnly value={publicKey} aria-label="Suzhou2 专用 SSH 公钥" />}
          {installCommand && <pre>{installCommand}</pre>}
          <small>只复制公钥或安装命令；不要上传本机私钥。</small>
        </div>}
        {paired && <div className="paired-summary">
          <div><span>服务器</span><strong>{executor?.user}@{executor?.host}:{executor?.port}</strong></div>
          <div><span>控制端</span><strong>{executor?.controller_id}</strong></div>
          <div><span>主机指纹</span><code>{executor?.host_fingerprint}</code></div>
          <button type="button" className="secondary-button" disabled={busy} onClick={() => void unpair()}>解除绑定并重新配置</button>
        </div>}
        {message && <div className="form-status">{message}</div>}
      </section>
    </div>
  );
}

function LocalEnvironmentSettings({
  installStatus,
  acceptedLicenses,
  onAcceptedLicensesChange,
  onInstall,
  message,
}: {
  installStatus?: InstallStatus;
  acceptedLicenses: string[];
  onAcceptedLicensesChange: (values: string[]) => void;
  onInstall: (component: string) => void;
  message: string;
}) {
  const components = COMPONENTS.map((component) => ({
    ...component,
    ...deriveComponentState(installStatus, component.id, acceptedLicenses),
  }));
  const required = components.filter((component) => component.group === "required");
  const workflow = components.filter((component) => component.group === "workflow");
  const requiredReady = required.every((component) => component.state === "available");
  const availableBackends = workflow.filter((component) => component.state === "available").length;
  const running = installStatus?.jobs.some((job) => job.status === "running");
  const lastJob = installStatus?.jobs[0];

  function renderComponent(component: typeof components[number]) {
    const plan = installStatus?.component_plans[component.id];
    const approvalsReady = component.approvals.every((item) => acceptedLicenses.includes(item.asset_id || ""));
    const canInstall = Boolean(plan?.disk.sufficient) && approvalsReady && component.state !== "running";
    return <article className="environment-component" key={component.id}>
      <div className="environment-component-main">
        <span className={`readiness-dot state-${component.state}`} aria-hidden="true" />
        <div><strong>{component.name}</strong><small>{component.description}</small></div>
      </div>
      <div className="environment-component-status">
        <span data-status={component.state}>{STATUS_LABELS[component.state]}</span>
        {!(["available", "running", "unsupported"] as ComponentState[]).includes(component.state) && <button
          type="button"
          disabled={!canInstall}
          onClick={() => onInstall(component.id)}
        >{plan?.disk.sufficient ? "安装" : "空间不足"}</button>}
      </div>
      {component.approvals.length > 0 && <div className="component-license-approvals">
        <strong>安装前需确认下列资产许可</strong>
        {component.approvals.map((item) => {
          const id = item.asset_id || "";
          return <label key={id}>
            <input
              type="checkbox"
              checked={acceptedLicenses.includes(id)}
              onChange={(event) => onAcceptedLicensesChange(
                event.target.checked
                  ? [...new Set([...acceptedLicenses, id])]
                  : acceptedLicenses.filter((value) => value !== id),
              )}
            />
            <span>{id}<small>{item.license || "未声明许可"}</small></span>
          </label>;
        })}
      </div>}
    </article>;
  }

  return <div className="settings-section-stack">
    <section className={`panel environment-summary ${requiredReady ? "available" : "attention"}`}>
      <div>
        <p className="section-label">当前设备</p>
        <h2>{installStatus ? requiredReady ? "基础环境已就绪" : "基础环境需要处理" : "正在检查当前设备…"}</h2>
        <p>{installStatus ? `已检测到 ${availableBackends} 个可用科学后端。新建设计时只会检查所选路线需要的工具。` : "EasyDesign 会自动读取工作区内的环境、模型和 GPU 状态。"}</p>
      </div>
      <div className="environment-summary-meta">
        <span>{running ? "安装任务进行中" : "状态自动更新"}</span>
        <small>{lastJob ? `最近任务 ${formatTime(lastJob.started_at)}` : "打开本页和返回窗口时重新检查"}</small>
      </div>
    </section>
    {installStatus?.plan && <div className={`settings-disk-note ${installStatus.plan.disk.sufficient ? "available" : "failed"}`}>
      <strong>{installStatus.plan.disk.sufficient ? "工作区磁盘正常" : "工作区磁盘不足"}</strong>
      <span>可用 {humanBytes(installStatus.plan.disk.free_bytes)} · 保留 {humanBytes(installStatus.plan.disk.reserve_bytes)} 安全余量</span>
    </div>}
    <section className="panel environment-group">
      <div className="panel-heading"><div><p className="section-label">必须</p><h3>基础运行环境</h3></div><span>{requiredReady ? "全部可用" : "需要处理"}</span></div>
      <div className="environment-component-list">{required.map(renderComponent)}</div>
    </section>
    <section className="panel environment-group">
      <div className="panel-heading"><div><p className="section-label">按需使用</p><h3>科学后端</h3></div><span>{availableBackends}/{workflow.length} 可用</span></div>
      <p className="environment-group-copy">不需要为了某条设计路线安装所有工具；缺失的无关后端不会阻止运行。</p>
      <div className="environment-component-list">{workflow.map(renderComponent)}</div>
    </section>
    {message && <div className="form-status settings-message">{message}</div>}
    <details className="panel settings-technical-details">
      <summary><span><strong>技术详情</strong><small>环境 ID、模型资产、安装任务和隔离区</small></span><b>展开</b></summary>
      <div className="technical-detail-body">
        <div className="technical-workspace"><span>工作区</span><code>{installStatus?.workspace || "正在读取"}</code></div>
        <div className="install-grid">
          <div><h4>环境记录</h4>{(installStatus?.environments || []).map((item) => <div className="install-row" key={item.environment_id}><strong>{item.environment_id}</strong><span data-status={item.status}>{item.status}</span></div>)}</div>
          <div><h4>资产记录</h4>{(installStatus?.assets || []).map((item) => <div className="install-row" key={item.asset_id}><span><strong>{item.asset_id}</strong><small>{item.license}</small></span><span data-status={item.status}>{item.status}</span></div>)}</div>
        </div>
        {!!installStatus?.jobs.length && <div className="setup-jobs"><h4>最近安装任务</h4>{installStatus.jobs.slice(0, 4).map((job) => <div className="install-row" key={job.job_id}><span><strong>{job.component || (job.minimal ? "core-ui" : "full")}</strong><small>{formatTime(job.started_at)}</small></span><span data-status={job.status}>{job.status}</span></div>)}</div>}
        <div className="quarantine-summary">隔离区：{installStatus?.quarantine.entries || 0} 项。EasyDesign 不会自动清理；任何清理都需要对精确路径另行批准。</div>
        <AssistantServiceCompact />
      </div>
    </details>
  </div>;
}

function AssistantServiceCompact() {
  const [status, setStatus] = useState<{ available: boolean; detail: string }>();
  useEffect(() => {
    void api.assistantStatus().then(setStatus).catch(() => setStatus({ available: false, detail: "平台助手状态暂时无法读取。" }));
  }, []);
  return <div className="assistant-service-compact"><span><strong>EasyDesign 结构助手</strong><small>API 由 EasyDesign 部署者统一提供，普通使用者无需填写 API Key。</small></span><b data-status={status?.available ? "available" : "not-installed"}>{status?.available ? "可用" : "未启用"}</b><p>{status?.detail || "正在检查…"}</p></div>;
}

export function SettingsPage({
  onBack,
  backLabel,
}: {
  onBack: () => void;
  backLabel: string;
}) {
  const [section, setSection] = useState<SettingsSection>("local");
  const [installStatus, setInstallStatus] = useState<InstallStatus>();
  const [catalog, setCatalog] = useState<ProjectCatalogEntry[]>([]);
  const [acceptedLicenses, setAcceptedLicenses] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [archiveQuery, setArchiveQuery] = useState("");

  async function refresh() {
    const [installResult, catalogResult] = await Promise.allSettled([
      api.installStatus(),
      api.projectCatalog(),
    ]);
    if (installResult.status === "fulfilled") setInstallStatus(installResult.value);
    if (catalogResult.status === "fulfilled") setCatalog(catalogResult.value.entries);
  }

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    void refresh();
    window.addEventListener("focus", refreshWhenVisible);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => {
      window.removeEventListener("focus", refreshWhenVisible);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!installStatus?.jobs.some((job) => job.status === "running")) return;
    const timer = window.setInterval(() => void refresh(), 2_000);
    return () => window.clearInterval(timer);
  }, [installStatus?.jobs]);

  async function launchSetup(component: string) {
    setMessage("正在建立安装任务…");
    try {
      const result = await api.launchSetup(false, component, acceptedLicenses);
      setMessage(`安装任务 ${result.job_id} 已启动，页面会自动更新状态。`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "安装任务启动失败");
    }
  }

  async function restore(entry: ProjectCatalogEntry) {
    setMessage(`正在恢复 ${entry.project_id}…`);
    try {
      await api.restoreProject(entry.project_id);
      await refresh();
      setMessage(`${entry.project_id} 已恢复到“我的项目”；科学文件和校验值没有改写。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "项目恢复失败");
    }
  }

  const archives = useMemo(() => catalog.filter((entry) =>
    entry.category === "archived-project-run"
    && entry.project_id.toLowerCase().includes(archiveQuery.trim().toLowerCase()),
  ), [archiveQuery, catalog]);

  return <div className="utility-page settings-page">
    <header className="page-heading compact">
      <div><p className="section-label">设置</p><h1>工作区设置</h1><p>查看当前设备、连接公共算力，或恢复已存档项目。</p></div>
      <button type="button" className="secondary-button" onClick={onBack}>← {backLabel}</button>
    </header>
    <nav className="settings-tabs" role="tablist" aria-label="设置页面">
      {([
        ["local", "当前设备", "自动检测环境与模型"],
        ["compute", "公共算力", "连接 Suzhou2"],
        ["archive", "项目存档", "查看并恢复已存档项目"],
      ] as const).map(([id, label, description]) => <button
        key={id}
        type="button"
        role="tab"
        aria-selected={section === id}
        className={section === id ? "selected" : ""}
        onClick={() => { setSection(id); setMessage(""); }}
      ><strong>{label}</strong><small>{description}</small></button>)}
    </nav>
    {section === "local" && <LocalEnvironmentSettings
      installStatus={installStatus}
      acceptedLicenses={acceptedLicenses}
      onAcceptedLicensesChange={setAcceptedLicenses}
      onInstall={(component) => void launchSetup(component)}
      message={message}
    />}
    {section === "compute" && <Suzhou2Settings />}
    {section === "archive" && <div className="settings-section-stack">
      <section className="panel archive-settings">
        <div className="panel-heading"><div><p className="section-label">可恢复存档</p><h2>项目存档</h2></div><span>{archives.length} 个项目</span></div>
        <div className="archive-toolbar"><label><span>搜索存档</span><input value={archiveQuery} onChange={(event) => setArchiveQuery(event.target.value)} placeholder="输入项目名称" /></label><p>存档只会从默认列表隐藏，不会删除运行或科学文件。</p></div>
        <div className="archive-list">
          {archives.map((entry) => <article key={entry.project_id}><div><strong>{entry.project_id}</strong><small>{entry.run_count} 次运行 · 完整性记录已保留</small></div><button type="button" onClick={() => void restore(entry)}>恢复到我的项目</button></article>)}
          {!archives.length && <div className="empty-state"><strong>{archiveQuery ? "没有匹配的存档" : "还没有存档项目"}</strong><span>可以在“我的项目”中将暂时不用的项目存档。</span></div>}
        </div>
      </section>
      {message && <div className="form-status settings-message">{message}</div>}
    </div>}
  </div>;
}
