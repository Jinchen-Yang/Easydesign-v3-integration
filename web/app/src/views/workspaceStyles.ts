/**
 * 工作区共用组件（features/*）的样式桶：Easy Live 与 Pro 都引用，
 * 由 Rollup 提升为两者共享的 CSS chunk，主包不再携带。
 */
import '../styles/compute.css';
import '../styles/context.css';
import '../styles/lab-order.css';
import '../styles/landing.css';
import '../styles/platform.css';
import '../styles/projects.css';
import '../styles/workspace.css';
