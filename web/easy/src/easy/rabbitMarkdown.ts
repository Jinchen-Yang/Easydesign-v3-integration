export type RabbitInlineToken =
  | { type: 'text'; value: string }
  | { type: 'strong'; value: string };

/** Parse Doudou's presentation-only emphasis without interpreting model text as HTML. */
export function parseRabbitInlineMarkdown(value: string): RabbitInlineToken[] {
  const tokens: RabbitInlineToken[] = [];
  let cursor = 0;

  while (cursor < value.length) {
    const opening = value.indexOf('**', cursor);
    if (opening === -1) {
      tokens.push({ type: 'text', value: value.slice(cursor) });
      break;
    }

    const closing = value.indexOf('**', opening + 2);
    if (closing === -1 || closing === opening + 2) {
      tokens.push({ type: 'text', value: value.slice(cursor) });
      break;
    }

    if (opening > cursor) {
      tokens.push({ type: 'text', value: value.slice(cursor, opening) });
    }
    tokens.push({ type: 'strong', value: value.slice(opening + 2, closing) });
    cursor = closing + 2;
  }

  return tokens;
}
