import React from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { App } from './App';
import { ToastProvider } from '@/components/Toast';
import { ThemeProvider } from './components/ThemeProvider';

const rootElement = document.getElementById('root');

if (rootElement) {
  createRoot(rootElement).render(
    <React.StrictMode>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <ToastProvider>
          <App />
        </ToastProvider>
      </ThemeProvider>
    </React.StrictMode>
  );
}
