import { describe, expect, it } from 'vitest';
import { parseRabbitInlineMarkdown } from '../src/easy/rabbitMarkdown';

describe('Doudou reply emphasis', () => {
  it('renders paired emphasis while retaining ordinary text and line breaks', () => {
    expect(parseRabbitInlineMarkdown('现在是 **Candidates** 阶段\n**请确认**')).toEqual([
      { type: 'text', value: '现在是 ' },
      { type: 'strong', value: 'Candidates' },
      { type: 'text', value: ' 阶段\n' },
      { type: 'strong', value: '请确认' },
    ]);
  });

  it('leaves incomplete markers and HTML-like text as plain text', () => {
    expect(parseRabbitInlineMarkdown('保留 **未闭合')).toEqual([
      { type: 'text', value: '保留 **未闭合' },
    ]);
    expect(parseRabbitInlineMarkdown('保留 **** 空标记')).toEqual([
      { type: 'text', value: '保留 **** 空标记' },
    ]);
    expect(parseRabbitInlineMarkdown('**<img src=x onerror=alert(1)>**')).toEqual([
      { type: 'strong', value: '<img src=x onerror=alert(1)>' },
    ]);
  });
});
