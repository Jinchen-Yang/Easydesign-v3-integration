import { createRoot } from 'react-dom/client';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import { App } from './app/App';
import { DemoAdapter } from './adapters/DemoAdapter';
import './styles/global.css';
import { LiveWorkbenchAdapter } from './adapters/LiveWorkbenchAdapter';
import { LiveWorkbench } from './live/LiveWorkbench';
import {AccountWorkbench} from './live/AccountWorkbench';
import {accountMode} from '../../shared/account-client';

let storage: Storage | undefined;
try {
  storage = window.localStorage;
} catch {
  /* Private browsing can disable storage; the in-memory demo still works. */
}
const demo = new URLSearchParams(location.search).get('mode') === 'demo';
createRoot(document.getElementById('root')!).render(
  demo ? (
    <App adapter={new DemoAdapter({ storage })} />
  ) : accountMode() ? (
    <AccountWorkbench />
  ) : (
    <LiveWorkbench adapter={new LiveWorkbenchAdapter()} />
  ),
);
