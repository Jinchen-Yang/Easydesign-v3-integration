import { createRoot } from 'react-dom/client';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import { App } from './app/App';
import { DemoAdapter } from './adapters/DemoAdapter';
import './styles/global.css';

let storage: Storage | undefined;
try {
  storage = window.localStorage;
} catch {
  /* Private browsing can disable storage; the in-memory demo still works. */
}
const adapter = new DemoAdapter({ storage });
createRoot(document.getElementById('root')!).render(<App adapter={adapter} />);
