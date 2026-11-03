import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles.css';
import './design-v1.css';
import './design-v2.css';
import './design-airbuild.css';

const root = document.getElementById('root');
if (!root) throw new Error('#root not found');

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
