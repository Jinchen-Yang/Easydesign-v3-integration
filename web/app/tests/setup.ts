import { beforeAll } from 'vitest';
import { loadAppNamespaces } from '../src/shell/I18nProvider';

// Synchronous component tests opt into eager dictionaries; browser tests exercise lazy route readiness.
beforeAll(() => loadAppNamespaces(['easy', 'pro', 'account']));

/**
 * Shared jsdom polyfills for the app test suite. jsdom does not implement
 * matchMedia, <dialog> methods or a real canvas 2D context; the demo
 * workbench (and the views it shares) touches all three while mounting.
 * Product code is never patched — these stubs only exist at test time.
 */

if (typeof window.matchMedia !== 'function') {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof matchMedia;
}

if (typeof HTMLDialogElement !== 'undefined' && !HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.setAttribute('open', '');
  };
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    this.removeAttribute('open');
  };
}

if (typeof HTMLCanvasElement !== 'undefined') {
  HTMLCanvasElement.prototype.getContext = function getContextStub(
    this: HTMLCanvasElement,
  ): CanvasRenderingContext2D | null {
    const canvas = this;
    return new Proxy(
      {},
      {
        get: (_target, property) => {
          if (property === 'canvas') return canvas;
          return () => undefined;
        },
        set: () => true,
      },
    ) as unknown as CanvasRenderingContext2D;
  } as unknown as HTMLCanvasElement['getContext'];
}

if (typeof HTMLElement.prototype.scrollTo !== 'function') {
  HTMLElement.prototype.scrollTo = function scrollToStub() {};
}
