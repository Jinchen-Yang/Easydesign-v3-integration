import { useCallback, useEffect, type ReactNode } from 'react';
import { I18nextProvider, useTranslation } from 'react-i18next';
import {
  createInstance,
  type i18n as I18nInstance,
  type PostProcessorModule,
  type BackendModule,
} from 'i18next';
import commonZh from '../locales/zh/common.json';
import commonEn from '../locales/en/common.json';

/**
 * Unified language authority (execution guide §2.4). One stable localStorage
 * preference shared with the legacy Easy demo (`easydesign-easy-locale-v1`),
 * so a user's existing choice carries into the new shell. Server-provided
 * content (project titles, targets, scientific text) is never translated.
 *
 * Only common text ships with the shell. Route namespaces are loaded by
 * i18next before useTranslation leaves Suspense. Each namespace loads both
 * locales together so synchronous getFixedT(locale) callers remain valid.
 */

export type Locale = 'zh' | 'en';
export const LANGUAGE_KEY = 'easydesign-easy-locale-v1';

function loadLocale(): Locale {
  try {
    return localStorage.getItem(LANGUAGE_KEY) === 'en' ? 'en' : 'zh';
  } catch {
    return 'zh';
  }
}

function saveLocale(locale: Locale): void {
  try {
    localStorage.setItem(LANGUAGE_KEY, locale);
  } catch {
    /* Optional preference; keep the active language in memory. */
  }
}

function documentLang(locale: Locale): string {
  return locale === 'zh' ? 'zh-CN' : 'en';
}

type RouteNamespace = 'easy' | 'pro' | 'account';
const namespaceLoaders = {
  easy: () => Promise.all([import('../locales/zh/easy.json'), import('../locales/en/easy.json')]),
  pro: () => Promise.all([import('../locales/zh/pro.json'), import('../locales/en/pro.json')]),
  account: () =>
    Promise.all([import('../locales/zh/account.json'), import('../locales/en/account.json')]),
};

function createAppI18n(): I18nInstance {
  const instance = createInstance();
  const loading = new Map<string, Promise<void>>();
  instance.use<BackendModule>({
    type: 'backend',
    init() {},
    read(language, namespace, callback) {
      const loader = namespaceLoaders[namespace as RouteNamespace];
      if (!loader || !['zh', 'en'].includes(language)) {
        callback(new Error('Unsupported UI locale or namespace'), false);
        return;
      }
      let pending = loading.get(namespace);
      if (!pending) {
        pending = loader().then(([zh, en]) => {
          instance.addResourceBundle('zh', namespace, zh.default);
          instance.addResourceBundle('en', namespace, en.default);
        });
        loading.set(namespace, pending);
        void pending.catch(() => loading.delete(namespace));
      }
      void pending.then(
        () => callback(null, instance.getResourceBundle(language, namespace)),
        (error) => callback(error as Error, false),
      );
    },
  });
  // The imported demo dictionary uses {name}; newer UI uses {{name}}.
  // Keep that compatibility at the language authority so React's t() and
  // the non-React Easy adapter produce identical, fully interpolated text.
  instance.use<PostProcessorModule>({
    type: 'postProcessor',
    name: 'legacyInterpolation',
    process(value, _key, options) {
      return value.replace(/(?<!\{)\{([A-Za-z_][\w]*)\}(?!\})/g, (token, name: string) => {
        if (!Object.prototype.hasOwnProperty.call(options, name)) return token;
        const replacement: unknown = options[name];
        return typeof replacement === 'string' || typeof replacement === 'number'
          ? String(replacement)
          : token;
      });
    },
  });
  void instance.init({
    lng: loadLocale(),
    // 英文即源文：英文缺译时回落为键本身（与旧演示 translate() 行为一致），
    // 绝不回落到中文。
    fallbackLng: false,
    ns: ['common'],
    partialBundledLanguages: true,
    defaultNS: 'common',
    resources: {
      zh: { common: commonZh },
      en: { common: commonEn },
    },
    // 扁平键：'e.g. 1MEL'、'guide.intake' 这类含点的键必须按字面解析。
    keySeparator: false,
    nsSeparator: false,
    interpolation: { escapeValue: false },
    postProcess: ['legacyInterpolation'],
    returnNull: false,
  });
  return instance;
}

/** 唯一 i18next 实例：React 之外的旧调用点（views/easy/i18n.ts 适配器）也用它。 */
export const appI18n = createAppI18n();

/** Explicit readiness boundary for non-React entrypoints and isolated tests. */
export async function loadAppNamespaces(namespaces: RouteNamespace[]): Promise<void> {
  await appI18n.loadNamespaces(namespaces);
}

export interface I18nContextValue {
  locale: Locale;
  changeLocale: (locale: Locale) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}

export function I18nProvider({ children }: { children?: ReactNode }) {
  const instance = appI18n;
  useEffect(() => {
    // 挂载时以持久化偏好为准（单例在测试/多挂载场景下不应带着旧语言）。
    const persisted = loadLocale();
    if ((instance.language === 'en' ? 'en' : 'zh') !== persisted) {
      void instance.changeLanguage(persisted);
    }
    document.documentElement.lang = documentLang(persisted);
  }, [instance]);
  return <I18nextProvider i18n={instance}>{children}</I18nextProvider>;
}

export function useI18n(): I18nContextValue {
  const { t, i18n } = useTranslation();
  const locale: Locale = i18n.language === 'en' ? 'en' : 'zh';
  const changeLocale = useCallback(
    (next: Locale) => {
      void i18n.changeLanguage(next);
      saveLocale(next);
      document.documentElement.lang = documentLang(next);
    },
    [i18n],
  );
  const translate = useCallback(
    (key: string, values?: Record<string, string | number>) => t(key, values ?? {}) as string,
    [t],
  );
  return { locale, changeLocale, t: translate };
}
