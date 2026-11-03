import { createRoot, Root } from 'react-dom/client';
import { createElement } from 'react';
import AgentCanvas from './AgentCanvas';
import { useCanvasStore } from './store';
import { readThemeWhitelist } from './conflict';
import xyflowCss from '@xyflow/react/dist/style.css?inline';
import localCss from './styles.css?inline';

export class AgentCanvasElement extends HTMLElement {
  static get observedAttributes(): string[] {
    return ['src'];
  }

  private root: Root | null = null;

  connectedCallback(): void {
    this.style.display = 'block';
    const shadow = this.shadowRoot ?? this.attachShadow({ mode: 'open' });

    let rootDiv = shadow.querySelector<HTMLDivElement>('[data-ac-root]');
    if (!rootDiv) {
      rootDiv = document.createElement('div');
      rootDiv.setAttribute('data-ac-root', '');
      rootDiv.style.width = '100%';
      rootDiv.style.height = '100%';
      rootDiv.style.minHeight = '480px';

      const theme = readThemeWhitelist(this);
      for (const key of Object.keys(theme)) {
        rootDiv.style.setProperty(key, theme[key]);
      }

      const style = document.createElement('style');
      style.textContent = `${xyflowCss}\n${localCss}`;

      shadow.appendChild(style);
      shadow.appendChild(rootDiv);
    }

    if (!this.root) {
      this.root = createRoot(rootDiv);
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
  customElements.define('agent-canvas', AgentCanvasElement);
}
