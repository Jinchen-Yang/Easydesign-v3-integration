import { appI18n } from '../../shell/I18nProvider';

/**
 * 旧演示的翻译入口，现在是统一 i18n 权威之上的薄适配层（根因 D 治理）：
 * 词典已迁入 locales/{zh,en}/easy.json，语言偏好由 I18nProvider 持久化，
 * 这里只保留 `translate(locale, key)` 这一调用形状给历史组件使用。
 */
export type Locale = 'zh' | 'en';
export const LANGUAGE_KEY = 'easydesign-easy-locale-v1';

export function translate(
  locale: Locale,
  key: string,
  values: Record<string, string | number> = {},
): string {
  const text = appI18n.getFixedT(locale, 'easy')(key, values);
  return typeof text === 'string' ? text : String(text);
}

export function loadLocale(): Locale {
  try {
    return localStorage.getItem(LANGUAGE_KEY) === 'en' ? 'en' : 'zh';
  } catch {
    return 'zh';
  }
}

export function saveLocale(locale: Locale) {
  try {
    localStorage.setItem(LANGUAGE_KEY, locale);
  } catch {
    /* Optional preference; keep the active language in memory. */
  }
}
