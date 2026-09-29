/**
 * Easy 面（演示 + Easy Live）共用的样式桶。两个路由各自懒加载时，
 * Rollup 会把这里引用的 CSS 提升成一个共享 chunk，只在进入 Easy 面时加载。
 */
import './easy.css';
import './product-live.css';
import './product-live-easy.css';
