import { useState } from 'react';
import { useI18n } from '../../shell/I18nProvider';
import { useSession } from '../../shell/SessionProvider';
import { EasyApp } from '../easy/EasyApp';
import { EasyDemoAdapter } from '../easy/EasyDemoAdapter';
import '../easy/easyStyles';

/**
 * 访客视图（执行指南阶段 4）：首页在未登录时直接渲染演示工作台，
 * 无需登录即可完整走通固定溶菌酶演示。
 *
 * 动作边界：访客用自有输入点「开始设计」时不会跑演示（演示结果只对
 * 固定示例有意义，草率模拟会误导），而是弹出登录引导；固定演示
 * （试用溶菌酶 · VHH）保持全流程可用。
 */
export function GuestView() {
  const { t } = useI18n();
  const { state } = useSession();
  const [prompt, setPrompt] = useState(false);
  const authenticated = state.kind === 'authenticated';

  function safeStorage(): Storage | undefined {
    try { return window.localStorage; } catch { return undefined; }
  }

  return (
    <div className="guest-view">
      <div className="guest-cta" role="region" aria-label={t('guest.ctaLabel')}>
        <span>{t('guest.cta')}</span>
        <a className="guest-cta-button" href="#/account">{t('guest.signIn')}</a>
      </div>
      <EasyApp
        adapter={new EasyDemoAdapter(safeStorage())}
        guardCustomSubmit={authenticated ? undefined : () => { setPrompt(true); return false; }}
      />
      {prompt && (
        <div className="guest-prompt-overlay" role="dialog" aria-modal="true" aria-label={t('guest.promptTitle')}>
          <div className="guest-prompt">
            <h2>{t('guest.promptTitle')}</h2>
            <p>{t('guest.promptBody')}</p>
            <a className="guest-prompt-primary" href="#/account">{t('guest.signIn')}</a>
            <button type="button" onClick={() => { setPrompt(false); }}>{t('guest.promptDemo')}</button>
          </div>
        </div>
      )}
    </div>
  );
}
