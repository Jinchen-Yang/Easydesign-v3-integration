import { createRoot } from 'react-dom/client';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import { EasyApp } from './easy/EasyApp';
import { EasyDemoAdapter } from './easy/EasyDemoAdapter';
import { EasyLiveApp } from './easy/EasyLiveApp';
import { EasyProductAdapter } from './easy/EasyProductAdapter';
import './styles/global.css';
import './easy/easy.css';
import './easy/product-live.css';
import './easy/product-live-easy.css';
let storage: Storage | undefined;
try {
  storage = window.localStorage;
} catch {
  /* In-memory preview remains available. */
}
const demo = new URLSearchParams(location.search).get('mode') === 'demo';
createRoot(document.getElementById('root')!).render(
  demo ? (
    <EasyApp adapter={new EasyDemoAdapter(storage)} />
  ) : (
    <EasyLiveApp adapter={new EasyProductAdapter()} />
  ),
);
