import React from 'react';
import { createRoot } from 'react-dom/client';
import 'antd/dist/reset.css';
import './styles.css';
import App from './App.jsx';

function showBootError(error) {
  if (typeof window.__smarterRpBootError === 'function') {
    window.__smarterRpBootError(error);
    return;
  }
  const root = document.getElementById('root');
  if (!root) {
    return;
  }
  const message = error instanceof Error ? error.stack || error.message : String(error);
  root.innerHTML = `<div class="boot-error"><strong>Smarter RP WebUI failed to load.</strong><pre>${message}</pre></div>`;
}

try {
  createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
} catch (error) {
  showBootError(error);
}
