import { createRoot } from 'react-dom/client';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import './styles/global.css';
import './styles/compute.css';
import './styles/context.css';
import './styles/lab-order.css';
import './styles/landing.css';
import './styles/platform.css';
import './styles/projects.css';
import './styles/workspace.css';
import './views/easy/easy.css';
import './views/easy/product-live.css';
import './views/easy/product-live-easy.css';
import './views/account/accounts.css';
import { AppShell } from './shell/AppShell';
import { applyLegacyRedirect } from './shell/legacyRedirect';

applyLegacyRedirect();

createRoot(document.getElementById('root')!).render(<AppShell />);
