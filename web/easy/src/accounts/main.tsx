import {createRoot} from 'react-dom/client';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '../styles/global.css';
import {AccountApp} from './AccountApp';

createRoot(document.getElementById('root')!).render(<AccountApp/>);
