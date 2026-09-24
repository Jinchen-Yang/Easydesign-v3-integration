import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { ConversationItem } from '../src/adapters/WorkbenchAdapter';
import { Conversation } from '../src/features/conversation/Conversation';

function render(item: ConversationItem) {
  return renderToStaticMarkup(
    createElement(Conversation, {
      mode: 'live',
      snapshot: { messages: [item], phase: 'target', busy: false, completed: false },
      viewedPhase: 'target',
      onFocus: () => undefined,
      onSend: () => undefined,
      onSkip: () => undefined,
    }),
  );
}

describe('live research activity status', () => {
  it('does not present a failed backend task as completed', () => {
    const html = render({
      id: 'failed-target',
      phase: 'target',
      kind: 'tool',
      title: 'Target Intelligence',
      text: 'Target research stopped temporarily.',
      status: 'failed',
    });
    expect(html).toContain('Failed');
    expect(html).not.toContain('Completed');
  });

  it('distinguishes running and approval-blocked activity', () => {
    expect(
      render({
        id: 'running-target',
        phase: 'target',
        kind: 'tool',
        text: 'Resolving evidence.',
        status: 'running',
      }),
    ).toContain('Running');
    expect(
      render({
        id: 'gate-target',
        phase: 'target',
        kind: 'tool',
        text: 'Scientist decision required.',
        status: 'blocked',
      }),
    ).toContain('Awaiting review');
  });
});
