import { describe, expect, it } from 'vitest';
import { parseRabbitInlineMarkdown } from '../src/easy/rabbitMarkdown';

describe('Doudou reply Markdown', () => {
  it('turns paired double asterisks into strong text', () => {
    expect(parseRabbitInlineMarkdown('现在是 **Candidates（候选分子）** 阶段')).toEqual([
      { type: 'text', value: '现在是 ' },
      { type: 'strong', value: 'Candidates（候选分子）' },
      { type: 'text', value: ' 阶段' },
    ]);
  });

  it('supports multiple bold spans and preserves line breaks', () => {
    expect(parseRabbitInlineMarkdown('**第一项**\n然后是 **第二项**')).toEqual([
      { type: 'strong', value: '第一项' },
      { type: 'text', value: '\n然后是 ' },
      { type: 'strong', value: '第二项' },
    ]);
  });

  it('leaves unmatched or empty markers visible', () => {
    expect(parseRabbitInlineMarkdown('保留 **未闭合')).toEqual([
      { type: 'text', value: '保留 **未闭合' },
    ]);
    expect(parseRabbitInlineMarkdown('保留 **** 空标记')).toEqual([
      { type: 'text', value: '保留 **** 空标记' },
    ]);
  });
});
