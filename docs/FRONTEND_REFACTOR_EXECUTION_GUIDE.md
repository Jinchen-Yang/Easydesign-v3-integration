# EasyDesign 前端重构执行指南

> **面向对象**：接手实现的 AI Agent  
> **目标**：将 Easy、Pro、账号门户合并为单一 SPA，解决九大痛点  
> **约束**：后端 Python 服务保持不变（除一处可选的滑动续期）  
> **日期**：2026-09-29

---

## 零、执行前必读

### 0.1 硬性约束（违反即失败）

| 约束 | 理由 | 验证方式 |
|-----|------|---------|
| **不改后端路由** | 后端只支持固定路由 | `git diff src/` 不应有路由新增 |
| **不删除旧 dist** | 需要回滚能力 | 旧 `ui-{commit}` 目录保留 |
| **不破坏现有 API** | 10 个交接账号正在使用 | e2e 测试必须全部通过 |
| **不静默迁移数据** | 草稿、项目数据不能自动合并 | 访客草稿独立命名空间 |

### 0.2 技术选型（不可改）

| 层级 | 技术栈 | 版本 | 理由 |
|-----|--------|------|------|
| 框架 | React | 19.0.0 | 已有 |
| 构建 | Vite | 6.1.0 | 已有 |
| 语言 | TypeScript | 5.7.3 | 已有 |
| 路由 | React Router | 6.x | Hash Router 模式 |
| 数据缓存 | TanStack Query | 5.x | 服务器状态管理 |
| 国际化 | i18next + react-i18next | 23.x | 扩展现有 i18n |

### 0.3 代码风格约束

- 复用现有组件而非重写（10 个 features 组件可直接迁移）
- 匹配现有命名风格（`AccountSession`、`WorkbenchAdapter`）
- 保持现有 Adapter 模式（`DemoAdapter`、`EasyProductAdapter`）
- CSS 继续使用普通 CSS，不引入 Tailwind 或 CSS-in-JS

---

## 一、架构全景

### 1.1 五层依赖关系（从上到下）

```
┌────────────────────────────────────────┐
│  1. 应用壳 (App Shell)                  │
│     - Hash Router                      │
│     - 会话状态机                        │
│     - 语言 Provider                     │
│     - 全局错误边界                      │
└────────────┬───────────────────────────┘
             │
┌────────────▼───────────────────────────┐
│  2. 视图层 (Views)                      │
│     - 访客视图（演示）                   │
│     - Easy Live                        │
│     - Pro                              │
│     - 账号与团队                        │
└────────────┬───────────────────────────┘
             │
┌────────────▼───────────────────────────┐
│  3. 数据层 (Data Layer)                 │
│     - TanStack Query 缓存               │
│     - 草稿恢复模块                       │
│     - 操作队列                          │
└────────────┬───────────────────────────┘
             │
┌────────────▼───────────────────────────┐
│  4. 适配层 (Adapters)                   │
│     - Account Client（复用）            │
│     - Product Adapter（复用）           │
└────────────┬───────────────────────────┘
             │
             ▼
      Python 后端（不动）
```

### 1.2 目录结构（最终状态）

```
web/
├── app/                    # 新的统一应用
│   ├── src/
│   │   ├── shell/          # 应用壳
│   │   │   ├── AppShell.tsx
│   │   │   ├── SessionProvider.tsx
│   │   │   ├── I18nProvider.tsx
│   │   │   └── Navigation.tsx
│   │   ├── views/          # 视图层
│   │   │   ├── guest/
│   │   │   ├── easy/
│   │   │   ├── pro/
│   │   │   └── account/
│   │   ├── data/           # 数据层
│   │   │   ├── queries.ts
│   │   │   ├── mutations.ts
│   │   │   └── draftRecovery.ts
│   │   ├── adapters/       # 适配层（从旧代码迁移）
│   │   └── shared/
│   │       └── types.ts
│   ├── index.html
│   └── vite.config.ts
├── easy/                   # 阶段 0-3 保留，阶段 5 删除
└── workbench/              # 阶段 0-3 保留，阶段 5 删除
```

---

## 二、核心模块接口契约

### 2.1 会话状态机 (SessionStateMachine)

**位置**：`app/src/shell/SessionProvider.tsx`

**状态定义**：
```typescript
type SessionState =
  | { kind: 'guest' }
  | { kind: 'checking' }
  | { 
      kind: 'authenticated';
      session: AccountSession;
      scope: AccountScope;
    }
  | {
      kind: 'expired';
      previousSession: AccountSession;
      recoverableData: Record<string, unknown>;
    }
  | { kind: 'network-error'; retry: () => void };
```

**状态转移规则**：
```
初始化 → checking
checking → guest | authenticated | network-error

guest → [登录成功] → authenticated

authenticated → [401] → expired
authenticated → [主动登出] → guest

expired → [重新登录同账号] → authenticated（恢复数据）
expired → [重新登录不同账号] → guest（清除数据）
expired → [取消恢复] → guest

network-error → [重试成功] → authenticated
network-error → [放弃] → guest
```

**对外接口**：
```typescript
interface SessionContext {
  state: SessionState;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  recoverSession: () => Promise<void>;
  dismissRecovery: () => void;
}

// React Hook
function useSession(): SessionContext;
```

**验收标准**：
- [ ] 单元测试：所有状态转移路径覆盖
- [ ] 401 触发 `expired` 状态（不跳转）
- [ ] 重新登录后恢复到原页面
- [ ] 换账号时清除旧数据

---

### 2.2 草稿恢复模块 (DraftRecovery)

**位置**：`app/src/data/draftRecovery.ts`

**接口定义**：
```typescript
interface DraftRecoveryModule {
  // 保存
  saveLocal(key: string, data: unknown): void;
  saveRemote(draft: ProjectDraft): Promise<void>;
  
  // 恢复
  recover(key: string): {
    hasLocal: boolean;
    hasRemote: boolean;
    data: unknown | null;
    savedAt: number | null;
  };
  
  // 清除
  clearLocal(key: string): void;
  clearAll(): void;
}
```

**存储策略**：
| 数据类型 | 本地存储 | 远程存储 | 恢复优先级 |
|---------|---------|---------|-----------|
| 项目创建输入 | sessionStorage | draftsApi | 远程优先 |
| Gate 审核备注 | sessionStorage | 无 | 仅本地 |
| 文件选择 | 文件引用 | 无 | 提示重新选择 |

**键命名规范**：
```
draft:project:create        # 项目创建草稿
draft:project:{id}:gate     # Gate 审核备注
draft:project:{id}:files    # 文件引用（路径 + size）
```

**验收标准**：
- [ ] 会话过期后本地草稿可恢复
- [ ] 远程草稿版本冲突时提示用户
- [ ] 换账号时不恢复旧账号的草稿
- [ ] 访客草稿独立命名空间（不与真实项目混淆）

---

### 2.3 Hash Router 路由表

**位置**：`app/src/shell/AppShell.tsx`

**路由定义**：
```typescript
const routes = [
  { path: '/', element: <RootRedirect /> },        // 重定向到 /#/
  { path: '/#/', element: <HomePage /> },          // 访客演示 / 项目列表
  { path: '/#/projects', element: <ProjectList /> },
  { path: '/#/projects/:id', element: <ProjectView /> }, // query: scope, view
  { path: '/#/account', element: <AccountView /> },
  { path: '/#/demo', element: <DemoView /> },
  { path: '*', element: <NotFound /> },
];
```

**query 参数约定**：
| 参数 | 含义 | 示例 |
|-----|------|------|
| `scope` | 团队/个人空间 ID | `?scope=u_xxx` |
| `view` | Easy / Pro 视图 | `?view=easy` |
| `project` | 项目 ID | `?project=p_xxx` |

**旧链接兼容**：
```typescript
// 应用启动时解析 location.pathname 和 location.search
function legacyRedirect() {
  const path = location.pathname;
  const params = new URLSearchParams(location.search);
  
  if (path === '/easy/') {
    const scope = params.get('scope');
    const project = params.get('project');
    if (project) {
      location.replace(`/#/projects/${project}?scope=${scope}&view=easy`);
    } else {
      location.replace(`/#/?scope=${scope}`);
    }
  }
  
  if (path === '/' && params.has('project')) {
    // 旧 Pro 链接
    location.replace(`/#/projects/${params.get('project')}?scope=${params.get('scope')}&view=pro`);
  }
  
  if (path === '/account/') {
    location.replace('/#/account');
  }
}
```

**验收标准**：
- [ ] 所有旧链接自动重定向到新路由
- [ ] 刷新页面后停留在当前路由
- [ ] 浏览器前进/后退正常工作
- [ ] 分享链接可直达指定项目

---

### 2.4 语言 Provider

**位置**：`app/src/shell/I18nProvider.tsx`

**接口定义**：
```typescript
interface I18nContext {
  locale: 'zh' | 'en';
  changeLocale: (locale: 'zh' | 'en') => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}

// React Hook
function useI18n(): I18nContext;
```

**词典结构**（复用 `easy/i18n.ts`）：
```
app/src/locales/
├── zh/
│   ├── common.json       # 导航、按钮、表单
│   ├── easy.json         # Easy Live（从 easy/i18n.ts 迁移）
│   ├── pro.json          # Pro 专属（新增英文翻译）
│   └── account.json      # 账号与团队（新增）
└── en/
    └── ...
```

**验收标准**：
- [ ] 语言切换后所有文本更新
- [ ] 不重新挂载组件（状态保留）
- [ ] 语言偏好持久化到 localStorage
- [ ] 服务器返回的内容（项目名、目标）不翻译

---

## 三、分阶段实施（4 个验收节点）

### 阶段 1：基础设施（验收节点 1）

**目标**：搭建应用壳，不影响现有页面。

**步骤清单**：
1. 创建 `web/app/` 目录
2. 配置 Vite（`web/app/vite.config.ts`）
3. 实现会话状态机（`SessionProvider.tsx`）
4. 实现草稿恢复模块（`draftRecovery.ts`）
5. 配置 React Router（Hash 模式）
6. 配置 i18next
7. 编写单元测试

**输入文件**：
- `web/shared/account-client.ts`（复用）
- `web/easy/src/easy/i18n.ts`（复用词典）

**输出文件**：
```
web/app/
├── src/
│   ├── shell/
│   │   ├── SessionProvider.tsx      # 会话状态机
│   │   ├── I18nProvider.tsx         # 语言 Provider
│   │   └── AppShell.tsx             # 空壳（仅路由）
│   ├── data/
│   │   └── draftRecovery.ts         # 草稿恢复
│   └── shared/
│       └── account-client.ts        # 从 web/shared 复制
├── tests/
│   ├── SessionProvider.test.tsx
│   └── draftRecovery.test.ts
├── index.html
├── package.json
├── vite.config.ts
└── tsconfig.json
```

**验收标准**（我来验收）：
```bash
# 1. 单元测试通过
cd web/app && pnpm test

# 2. 会话状态机覆盖所有转移路径
# 检查点：SessionProvider.test.tsx 包含以下场景
# - guest → authenticated
# - authenticated → expired → authenticated（同账号）
# - authenticated → expired → guest（换账号）
# - 401 不跳转，触发 expired 状态

# 3. 草稿恢复本地存储可用
# 检查点：draftRecovery.test.ts 包含
# - saveLocal + recover
# - clearAll 清除所有草稿
# - 访客草稿独立命名空间

# 4. 应用可启动（空壳）
cd web/app && pnpm dev
# 访问 http://localhost:13200 看到 "App Shell Loading..."
```

---

### 阶段 2：止血修复（验收节点 2）

**目标**：解决痛点④⑤，立即可用。

**步骤清单**：
1. 修改 `account-client.ts` 的 `scopedTransport`：401 时发出事件而非跳转
2. 创建 401 恢复遮罩组件（`SessionRecoveryModal.tsx`）
3. 实现 `?next=` 机制（登录成功后回跳）
4. **可选**：后端滑动续期（`accounts.py` 一行改动）

**代码改动**：

**文件 1**：`web/app/src/shared/account-client.ts`
```typescript
// 原代码（scopedTransport）：
if (response.status === 401) {
  notifySessionChange();
  location.replace(accountLoginUrl());  // ❌ 删除这行
}

// 新代码：
if (response.status === 401) {
  notifySessionChange();
  // ✅ 发出事件而非跳转
  window.dispatchEvent(new CustomEvent('easydesign:session-expired', {
    detail: { session, scope }
  }));
}
```

**文件 2**：`web/app/src/shell/SessionRecoveryModal.tsx`
```typescript
export function SessionRecoveryModal() {
  const { state, recoverSession, dismissRecovery } = useSession();
  
  if (state.kind !== 'expired') return null;
  
  return (
    <div className="session-recovery-overlay">
      <div className="session-recovery-modal">
        <h2>会话已过期</h2>
        <p>请重新登录以继续操作</p>
        <form onSubmit={handleLogin}>
          <input type="password" placeholder="密码" />
          <button type="submit">登录</button>
          <button type="button" onClick={dismissRecovery}>取消</button>
        </form>
        <p className="recovery-hint">
          未保存的输入已暂存，登录后将自动恢复
        </p>
      </div>
    </div>
  );
}
```

**文件 3**：`web/app/src/shell/SessionProvider.tsx`
```typescript
// 监听 401 事件
useEffect(() => {
  const handle401 = (event: CustomEvent) => {
    const { session } = event.detail;
    
    // 保存当前路由
    localStorage.setItem('easydesign-recovery-path', location.hash);
    
    // 保存可恢复的数据
    const recoverable = draftRecovery.recoverAll();
    
    setState({
      kind: 'expired',
      previousSession: session,
      recoverableData: recoverable,
    });
  };
  
  window.addEventListener('easydesign:session-expired', handle401);
  return () => window.removeEventListener('easydesign:session-expired', handle401);
}, []);
```

**后端可选改动**（滑动续期）：
```python
# src/easydesign/product/accounts.py:523 附近
def authenticate(self, token: str) -> AccountUser:
    with self.db as cursor:
        cursor.execute(
            "SELECT u.id, ... FROM users u JOIN sessions s ... "
            "WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? ",
            (token_hash, current_time),
        )
        row = cursor.fetchone()
        if not row:
            raise AccountError("unauthorized", "会话已失效", 401)
        
        # ✅ 新增：滑动续期（可选）
        cursor.execute(
            "UPDATE sessions SET expires_at=? WHERE token_hash=?",
            (current_time + SESSION_TTL, token_hash),
        )
    
    return AccountUser(...)
```

**验收标准**（我来验收）：
```bash
# 1. 会话过期后不跳转
# 手动测试：
# - 启动应用，登录
# - 后端手动设置会话过期（或等 7 天）
# - 发起任意请求
# - 期望：弹出恢复遮罩，页面不跳转

# 2. 重新登录后恢复
# 检查点：
# - 恢复遮罩中输入密码登录
# - 返回原页面（路由不变）
# - 草稿输入恢复

# 3. 换账号时清除旧数据
# 检查点：
# - 在恢复遮罩中用不同账号登录
# - 旧账号的项目、草稿不显示

# 4. 滑动续期生效（如果实现）
# 检查点：
# - 登录后 3 天内持续使用
# - 会话未过期（从数据库验证 expires_at 有更新）
```

---

### 阶段 3：统一壳 + 视图迁移（验收节点 3）

**目标**：Easy、Pro、账号门户在同一应用切换。

**步骤清单**：
1. 迁移 Easy Live 到 `app/src/views/easy/`
2. 迁移 Pro 到 `app/src/views/pro/`
3. 迁移账号门户到 `app/src/views/account/`
4. 实现顶部导航（`Navigation.tsx`）
5. 配置 TanStack Query（项目列表、候选列表）
6. 实现旧链接重定向

**迁移规则**：
| 原路径 | 新路径 | 改动 |
|-------|--------|------|
| `web/easy/src/easy/*` | `app/src/views/easy/*` | 直接复制 |
| `web/easy/src/features/*` | `app/src/views/easy/features/*` | 直接复制 |
| `web/easy/src/adapters/*` | `app/src/adapters/*` | 合并（去重） |
| `web/workbench/src/live/*` | `app/src/views/pro/*` | 直接复制 |
| `web/workbench/src/features/*` | ❌ 不复制 | 复用 Easy 的 features |
| `web/easy/src/accounts/*` | `app/src/views/account/*` | 直接复制 |

**输出文件**：
```
web/app/src/
├── views/
│   ├── easy/
│   │   ├── EasyLiveApp.tsx          # 从 web/easy 迁移
│   │   ├── features/                # 10 个组件
│   │   └── ...
│   ├── pro/
│   │   ├── LiveWorkbench.tsx        # 从 web/workbench 迁移
│   │   └── ...
│   └── account/
│       ├── AccountApp.tsx           # 从 web/easy/accounts 迁移
│       └── ...
├── shell/
│   └── Navigation.tsx               # 顶部导航
└── adapters/                         # 合并后的 Adapter
```

**验收标准**（我来验收）：
```bash
# 1. 三个视图都可访问
# 手动测试：
# - 访问 /#/ → 看到项目列表（已登录）或演示（访客）
# - 访问 /#/projects/xxx?view=easy → Easy Live
# - 访问 /#/projects/xxx?view=pro → Pro
# - 访问 /#/account → 账号与团队

# 2. 视图间切换不刷新
# 检查点：
# - Easy → Pro 切换时网络请求不重复
# - 项目列表 → 账号 → 项目列表，列表状态保留

# 3. 旧链接自动重定向
# 测试用例：
curl -I http://localhost:13200/easy/?scope=u_1&project=p_1
# 期望：302 重定向到 /#/projects/p_1?scope=u_1&view=easy

# 4. 语言切换生效
# 检查点：
# - 点击语言切换按钮
# - 所有视图的文本同步更新
# - 不重新加载项目数据
```

---

### 阶段 4：访客态 + demo 转正（验收节点 4，最终验收）

**目标**：首页可见，访客可体验演示。

**步骤清单**：
1. 创建访客视图（`views/guest/GuestView.tsx`）
2. 将 demo 模式转为访客视图（复用 `EasyApp.tsx`）
3. 修复 demo 死链（`127.0.0.1:13180` → 相对路径）
4. 添加登录 CTA
5. 动作边界鉴权（提交设计、批准 Gate 时检查登录）

**代码改动**：

**文件 1**：`app/src/views/guest/GuestView.tsx`
```typescript
export function GuestView() {
  const { state } = useSession();
  
  // 访客看到演示，已登录看到项目列表
  if (state.kind === 'authenticated') {
    return <Navigate to="/#/projects" />;
  }
  
  return (
    <div className="guest-view">
      <DemoWorkbench />
      <LoginCTA />
    </div>
  );
}
```

**文件 2**：修复 demo 死链
```typescript
// 原代码（EasyApp.tsx:262）：
href="http://127.0.0.1:13180/#projects"

// 新代码：
href="/#/projects"  // 相对路径
```

**文件 3**：动作边界鉴权
```typescript
// 在 EasyLiveApp.tsx 和 LiveWorkbench.tsx 中
function handleSubmitDesign() {
  const { state } = useSession();
  
  if (state.kind !== 'authenticated') {
    // ✅ 访客试图提交时显示登录提示
    showLoginPrompt('登录后可提交真实设计任务');
    return;
  }
  
  // 已登录用户继续提交
  submitDesign();
}
```

**验收标准**（我来验收，这是最终验收）：
```bash
# 1. 首页可见（痛点 ① 解决）
# 测试：访问 http://localhost:13200/
# 期望：立即看到演示工作台，无需登录

# 2. demo 可用（痛点 ② 解决）
# 检查点：
# - 演示流程完整可走通
# - "专业版"链接指向 /#/projects（不再是 127.0.0.1:13180）
# - 演示内有登录入口

# 3. 访客提交时提示登录
# 检查点：
# - 访客点击"开始设计"
# - 弹出登录提示："登录后可提交真实设计任务"
# - 点击登录后跳转到登录页，登录成功返回原页面

# 4. e2e 测试全部通过
cd web/app && pnpm test:e2e

# 5. 旧账号可正常使用
# 手动测试：
# - 用交接的 10 个账号分别登录
# - 可查看项目列表
# - 可创建项目
# - 可切换 Easy/Pro 视图
# - 会话过期后可恢复

# 6. 性能不退化
# 检查点：
# - 首屏加载时间 < 2s（本地开发环境）
# - 项目列表切换 < 500ms
# - bundle 大小 < 1MB（gzip 后）

# 7. 回滚能力验证
# 检查点：
# - 旧 `ui-{commit}` 目录仍存在
# - 后端可切换回旧版本（修改路由配置）
# - 旧版本仍可正常使用
```

---

## 四、注意事项与边界

### 4.1 必须遵守的边界

| 边界 | 说明 | 违反后果 |
|-----|------|---------|
| **不改后端路由** | 不添加新的 URL pattern | 部署失败 |
| **不破坏 API 契约** | 不修改请求/响应格式 | 现有用户受影响 |
| **不自动迁移数据** | 访客草稿 ≠ 真实项目 | 数据污染 |
| **不删除旧构建产物** | 保留回滚能力 | 无法回滚 |

### 4.2 可以做的事

| 操作 | 约束 |
|-----|------|
| 添加新组件 | 放在 `app/src/` 下 |
| 复用旧组件 | 从 `web/easy`、`web/workbench` 迁移 |
| 修改 `account-client.ts` | 只改 401 处理，不改 API 调用 |
| 添加依赖 | React Router、TanStack Query、i18next |
| 修改 CSS | 复用现有 CSS 文件，不引入 CSS 框架 |

### 4.3 风险与缓解

| 风险 | 概率 | 缓解措施 |
|-----|------|---------|
| Hash Router 与后端冲突 | 低 | 提前在 dev 环境验证 |
| 会话恢复逻辑复杂 | 中 | 单元测试 + e2e 测试覆盖 |
| 旧链接兼容遗漏 | 中 | 整理所有已知链接形式，逐一测试 |
| 草稿版本冲突 | 低 | 乐观锁 + 冲突提示 |

### 4.4 遇到问题时的决策树

```
遇到技术问题
├─ 是否违反硬性约束？
│   ├─ 是 → 停止，找其他方案
│   └─ 否 → 继续
├─ 现有代码能复用吗？
│   ├─ 能 → 优先复用
│   └─ 否 → 实现新逻辑
└─ 需要添加依赖吗？
    ├─ 必须 → 选择最小依赖
    └─ 可选 → 手写实现
```

---

## 五、验收检查清单

### 验收节点 1：基础设施

- [ ] `web/app/` 目录存在
- [ ] `pnpm test` 通过
- [ ] 会话状态机单元测试覆盖所有转移路径
- [ ] 草稿恢复模块测试覆盖本地存储
- [ ] `pnpm dev` 可启动空壳应用

### 验收节点 2：止血修复

- [ ] 401 触发恢复遮罩（不跳转）
- [ ] 重新登录后回到原页面
- [ ] 草稿输入恢复
- [ ] 换账号时清除旧数据
- [ ] 滑动续期生效（如果实现）

### 验收节点 3：统一壳

- [ ] 三个视图（Easy/Pro/账号）可访问
- [ ] 视图间切换不刷新页面
- [ ] 旧链接自动重定向
- [ ] 语言切换实时生效

### 验收节点 4：最终验收

- [ ] 首页可见（访客演示）
- [ ] demo 可用（死链修复）
- [ ] 访客提交时提示登录
- [ ] e2e 测试全部通过
- [ ] 10 个交接账号可正常使用
- [ ] 性能不退化
- [ ] 回滚能力验证

---

## 六、交付清单

### 代码交付

```
web/app/
├── src/                    # 源代码
├── tests/                  # 单元测试 + e2e 测试
├── package.json
├── vite.config.ts
└── tsconfig.json
```

### 文档交付

- [ ] `README.md` — 启动指南
- [ ] `ARCHITECTURE.md` — 架构说明
- [ ] `MIGRATION.md` — 从旧版本迁移指南
- [ ] e2e 测试报告

### 验收材料

- [ ] 4 个验收节点的截图/录屏
- [ ] 单元测试覆盖率报告（> 80%）
- [ ] e2e 测试通过截图
- [ ] 性能对比数据（旧版 vs 新版）

---

## 七、时间估算

| 阶段 | 工作量 | 累计 |
|-----|--------|------|
| 阶段 1：基础设施 | 1-2 天 | 1-2 天 |
| 阶段 2：止血修复 | 2-3 天 | 3-5 天 |
| 阶段 3：统一壳 | 5-7 天 | 8-12 天 |
| 阶段 4：访客态 | 5-7 天 | 13-19 天 |
| **总计** | **3-4 周** | |

---

## 八、FAQ

### Q1：为什么用 Hash Router 而不是 Browser History？

**A**：后端只支持固定路由（`/`、`/easy/`、`/account/`），不支持通配符。Browser History 需要后端配置 catch-all 路由，违反"不改后端"约束。

### Q2：TanStack Query 必须用吗？

**A**：不是必须，但强烈推荐。手动管理缓存、去重、刷新会增加代码复杂度。如果不用，需要自己实现等价功能。

### Q3：旧代码什么时候删除？

**A**：在阶段 4 验收通过后，保留 2 周观察期。确认无问题后执行阶段 5 清理。

### Q4：如果验收不通过怎么办？

**A**：回到对应阶段，修复问题后重新验收。每个阶段独立，不影响后续阶段。

### Q5：后端滑动续期是可选的吗？

**A**：是的。如果不实现，会话仍固定 7 天 TTL。前端的 401 恢复机制仍生效，只是需要用户更频繁地重新登录。

---

## 九、结语

这份文档是执行级别的指南，可以直接交给其他 AI 去实现。关键点：

1. **模块接口明确** — 输入输出、状态转移、验收标准都清晰定义
2. **分步可验收** — 4 个验收节点，每个节点独立可测试
3. **边界清晰** — 什么能做、什么不能做、违反后果都说明了
4. **风险可控** — 渐进式重构，每阶段可回滚

我会在 4 个验收节点检查代码和功能。你只需要把这份文档交给其他 AI，让它们按步骤实现即可。

有问题随时找我。
