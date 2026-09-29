import { createRoot } from 'react-dom/client';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import './styles/global.css';
import { AppShell } from './shell/AppShell';
import { applyLegacyRedirect } from './shell/legacyRedirect';

// 视图级 CSS 已随各自的懒加载块拆出（views/*/…Styles.ts、组件内 import），
// 主包只保留基础重置与应用壳样式。
applyLegacyRedirect();

createRoot(document.getElementById('root')!).render(<AppShell />);
