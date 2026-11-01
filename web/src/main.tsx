import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { createApi, createHttpTransport } from './api/client';
import { createMockTransport } from './mock/api';
import './styles.css';

const mock = import.meta.env.VITE_USE_MOCK !== 'false';
const api = createApi(mock ? createMockTransport() : createHttpTransport(import.meta.env.VITE_API_URL));
createRoot(document.getElementById('root')!).render(<StrictMode><App api={api} mock={mock} /></StrictMode>);
