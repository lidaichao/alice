import React from 'react';
import { StrictMode } from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';

const { createRoot } = ReactDOM;

try {
  const root = document.getElementById('root');
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
} catch (e) {
  document.getElementById('root').innerHTML =
    '<div style="color:red;padding:24px;">Error: ' + e.message + '</div>';
}
