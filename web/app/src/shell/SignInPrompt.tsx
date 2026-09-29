import { useI18n } from './I18nProvider';

/**
 * 统一的登录引导屏：访客试图进入需要真实数据的界面（工作区、项目列表）
 * 时展示。这是动作/资源边界的产品化呈现——不再整页跳转回旧门户。
 */
export function SignInPrompt({
  title, description, backHref, backLabel,
}: {
  title: string;
  description: string;
  backHref?: string;
  backLabel?: string;
}) {
  const { t } = useI18n();
  return (
    <main className="account-login">
      <h1>{title}</h1>
      <p>{description}</p>
      <a className="account-primary" href="#/account">{t('prompt.signIn')}</a>
      <a href={backHref ?? '#/'}>{backLabel ?? t('prompt.backToDemo')}</a>
    </main>
  );
}
