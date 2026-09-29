import { useCallback, useEffect, useMemo, type ReactNode } from 'react';
import { I18nextProvider, useTranslation } from 'react-i18next';
import { createInstance, type i18n as I18nInstance } from 'i18next';
import commonZh from '../locales/zh/common.json';
import easyZh from '../locales/zh/easy.json';
import proZh from '../locales/zh/pro.json';
import accountZh from '../locales/zh/account.json';
import commonEn from '../locales/en/common.json';
import easyEn from '../locales/en/easy.json';
import proEn from '../locales/en/pro.json';
import accountEn from '../locales/en/account.json';

/**
 * Unified language authority (execution guide §2.4). One stable localStorage
 * preference shared with the legacy Easy demo (`easydesign-easy-locale-v1`),
 * so a user's existing choice carries into the new shell. Server-provided
 * content (project titles, targets, scientific text) is never translated.
 *
 * easy/pro/account namespaces ship as placeholders in phase 1; their
 * dictionaries migrate together with the views in phase 3.
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

function createAppI18n(): I18nInstance {
  const instance = createInstance();
  void instance.init({
    lng: loadLocale(),
    fallbackLng: 'zh',
    ns: ['common', 'easy', 'pro', 'account'],
    defaultNS: 'common',
    resources: {
      zh: { common: commonZh, easy: easyZh, pro: proZh, account: accountZh },
      en: { common: commonEn, easy: easyEn, pro: proEn, account: accountEn },
    },
    interpolation: { escapeValue: false },
    returnNull: false,
  });
  return instance;
}

export interface I18nContextValue {
  locale: Locale;
  changeLocale: (locale: Locale) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}

export function I18nProvider({ children }: { children?: ReactNode }) {
  const instance = useMemo(createAppI18n, []);
  useEffect(() => {
    document.documentElement.lang = documentLang(instance.language === 'en' ? 'en' : 'zh');
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
