import React from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { MobileApp } from './MobileApp';
import { ThemeProvider } from './components/ThemeProvider';

const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <React.StrictMode>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <MobileApp />
      </ThemeProvider>
    </React.StrictMode>
  );
}
