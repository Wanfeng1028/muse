import { createRoot, Root } from 'react-dom/client';
import { createElement } from 'react';
import AgentCanvas from './AgentCanvas';
import { useCanvasStore } from './store';
import xyflowCss from '@xyflow/react/dist/style.css?inline';
import localCss from './styles.css?inline';

const STYLE_ID = 'agent-canvas-styles';

function injectStylesOnce(): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `${xyflowCss}\n${localCss}`;
  document.head.appendChild(style);
}

export class AgentCanvasElement extends HTMLElement {
  static get observedAttributes(): string[] {
    return ['src'];
  }

  private container: HTMLDivElement | null = null;
  private root: Root | null = null;

  connectedCallback(): void {
    this.style.display = 'block';
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.style.width = '100%';
      this.container.style.height = '100%';
      this.container.style.minHeight = '480px';
      this.appendChild(this.container);
    }
    if (!this.root) {
      this.root = createRoot(this.container);
      this.root.render(createElement(AgentCanvas));
    }
    const src = this.getAttribute('src');
    if (src) {
      void useCanvasStore.getState().load(src);
    }
  }

  disconnectedCallback(): void {
    if (this.root) {
      this.root.unmount();
      this.root = null;
    }
  }

  attributeChangedCallback(
    name: string,
    oldValue: string | null,
    newValue: string | null,
  ): void {
    if (name === 'src' && oldValue !== newValue && newValue) {
      void useCanvasStore.getState().load(newValue);
    }
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('agent-canvas')) {
  injectStylesOnce();
  customElements.define('agent-canvas', AgentCanvasElement);
}
