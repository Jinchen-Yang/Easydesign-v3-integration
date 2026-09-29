import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import ts from 'typescript';
import { I18nProvider, appI18n, LANGUAGE_KEY } from '../src/shell/I18nProvider';
import { translate } from '../src/views/easy/i18n';
import { ProjectsPage } from '../src/features/projects/ProjectsPage';
import { GateReview } from '../src/views/pro/GateReview';
import { Conversation } from '../src/features/conversation/Conversation';
import type { Decision } from '../src/data/product-contracts';
import common from '../src/locales/zh/common.json';
import easy from '../src/locales/zh/easy.json';
import pro from '../src/locales/zh/pro.json';

const dictionaries: Record<string, Record<string, string>> = {
  common,
  easy,
  pro,
};
const sourceFiles = (directory: string): string[] =>
  readdirSync(directory, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory()
      ? sourceFiles(join(directory, entry.name))
      : /\.tsx?$/.test(entry.name)
        ? [join(directory, entry.name)]
        : [],
  );
const placeholders = (value: string) =>
  [...new Set([...value.matchAll(/\{\{?(\w+)\}?\}/g)].map((match) => match[1]))].sort();
afterEach(cleanup);

async function language(locale: 'zh' | 'en') {
  localStorage.setItem(LANGUAGE_KEY, locale);
  await act(() => appI18n.changeLanguage(locale));
}

describe('language contract', () => {
  it('covers literal UI keys in both workspaces and keeps interpolation variables intact', () => {
    const missing: string[] = [];
    for (const file of sourceFiles(join(process.cwd(), 'src'))) {
      const source = readFileSync(file, 'utf8');
      const namespace =
        source.match(/useTranslation\(\s*(?:\[\s*)?['"](pro|easy)['"]/)?.[1] ??
        (file.includes('/views/easy/') ? 'easy' : null);
      const ast = ts.createSourceFile(
        file,
        source,
        ts.ScriptTarget.Latest,
        true,
        ts.ScriptKind.TSX,
      );
      const visit = (node: ts.Node) => {
        if (
          ts.isCallExpression(node) &&
          node.arguments[0] &&
          ts.isStringLiteral(node.arguments[0])
        ) {
          const fn = node.expression.getText(ast);
          const ns =
            fn === 'commonT' ? 'common' : fn === 'easyT' ? 'easy' : fn === 't' ? namespace : null;
          const key = node.arguments[0].text;
          if (ns && !Object.hasOwn(dictionaries[ns], key)) missing.push(`${file}: ${ns}: ${key}`);
        }
        ts.forEachChild(node, visit);
      };
      visit(ast);
    }
    expect(missing).toEqual([]);
    for (const dictionary of Object.values(dictionaries)) {
      for (const [key, value] of Object.entries(dictionary)) {
        expect(value.trim(), key).not.toBe('');
        // Legacy symbolic common keys intentionally carry values not present in the key.
        if (
          !key.startsWith('shell.') &&
          !key.startsWith('placeholder.') &&
          !key.startsWith('recovery.')
        )
          expect(placeholders(value), key).toEqual(placeholders(key));
      }
    }
  });

  it('interpolates legacy demo placeholders through both React and non-React translation paths', () => {
    expect(
      translate('zh', 'Step {number} of 6: {stage}', {
        number: 2,
        stage: '位点',
      }),
    ).toBe('第 2 / 6 阶段：位点');
    expect(appI18n.getFixedT('en', 'easy')('Open {name}', { name: 'Candidate A' })).toBe(
      'Open Candidate A',
    );
    expect(
      translate('zh', '{{completed}} / {{total}} candidates', {
        completed: 0,
        total: 8,
      }),
    ).toBe('0 / 8 条');
    expect(translate('en', 'Open {name}', { name: '$& {stage} <img>' })).toBe(
      'Open $& {stage} <img>',
    );
    expect(translate('en', '{constructor}')).toBe('{constructor}');
  });

  it('switches project controls without rewriting project titles or research goals', async () => {
    await language('zh');
    const onOpen = vi.fn();
    render(
      <I18nProvider>
        <ProjectsPage
          mode="live"
          onNew={vi.fn()}
          onOpen={onOpen}
          snapshot={{
            projects: [
              {
                id: 'p1',
                title: 'Design Scientist',
                goal: 'Native goal: preserve pH 7.4.',
                phase: 'pilot',
                status: 'review',
              },
            ],
          }}
        />
      </I18nProvider>,
    );
    expect(screen.getByRole('heading', { name: '项目' })).toBeTruthy();
    expect(screen.getByText('待审核')).toBeTruthy();
    expect(screen.getByText('Native goal: preserve pH 7.4.')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Design Scientist' })).toBeTruthy();
    await language('en');
    expect(screen.getByRole('heading', { name: 'Projects' })).toBeTruthy();
    expect(screen.getByText('Ready for review')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Open project Design Scientist' }));
    expect(onOpen).toHaveBeenCalledWith('p1');
  });

  it('translates Gate action labels without changing submitted action identifiers or scientific evidence', async () => {
    await language('zh');
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const decision: Decision = {
      id: 'scientific-card',
      gate: 2,
      type: 'site',
      question: 'Design Scientist',
      default_option_id: 'site-a',
      options: [
        {
          option_id: 'site-a',
          label: 'Native site α',
          eligible: true,
          actions: ['revise', 'approve'],
        },
      ],
      warnings: ['Retain original evidence.'],
      limitations: [],
      action_summary: 'Native scientific summary.',
      revision_targets: ['site-hotspot'],
      review_status: 'SUPPORTED',
      required_fields: {},
      summary: {},
    };
    render(
      <I18nProvider>
        <GateReview decision={decision} busy={false} onSelect={vi.fn()} onSubmit={onSubmit} />
      </I18nProvider>,
    );
    expect(screen.getByRole('heading', { name: 'Design Scientist' })).toBeTruthy();
    expect(screen.getByText('Native scientific summary.')).toBeTruthy();
    const option = screen.getByRole('option', {
      name: '批准',
    }) as HTMLOptionElement;
    expect(option.value).toBe('approve');
    fireEvent.change(screen.getByRole('combobox', { name: '决策操作' }), {
      target: { value: 'approve' },
    });
    await act(async () => fireEvent.click(screen.getByRole('button', { name: '提交批准' })));
    expect(onSubmit).toHaveBeenCalledWith({
      action: 'approve',
      selected_option_id: 'site-a',
    });
    await language('en');
    expect(screen.getByRole('option', { name: 'Approve' })).toBeTruthy();
  });

  it('keeps live model answers and user input verbatim even when they match a translated UI key', async () => {
    await language('zh');
    render(
      <I18nProvider>
        <Conversation
          mode="live"
          viewedPhase="goal"
          onFocus={vi.fn()}
          onSend={vi.fn()}
          onSkip={vi.fn()}
          snapshot={{
            phase: 'goal',
            busy: false,
            completed: false,
            messages: [
              {
                id: 'user',
                phase: 'goal',
                kind: 'user',
                text: 'Design Scientist',
              },
              {
                id: 'answer',
                phase: 'goal',
                kind: 'summary',
                title: 'Native summary',
                text: 'Design Scientist',
              },
            ],
          }}
        />
      </I18nProvider>,
    );
    expect(screen.getAllByText('Design Scientist')).toHaveLength(2);
    expect(screen.getByRole('heading', { name: '设计科学家' })).toBeTruthy();
    await language('en');
    expect(screen.getByRole('heading', { name: 'Design Scientist' })).toBeTruthy();
  });
});
