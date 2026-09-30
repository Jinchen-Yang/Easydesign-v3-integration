import { appI18n } from "../../shell/I18nProvider";
export const isEnglish = () => appI18n.language.startsWith("en");
export const ui = (
  text: string,
  values: Record<string, unknown> = {},
): string => appI18n.t(text, { ns: "easy", ...values });
