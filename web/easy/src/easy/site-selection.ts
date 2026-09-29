import type { Decision, Site } from './product-contracts';

/**
 * A hard-blocked portfolio entry intentionally has no scientific rank. The Easy
 * surface still gives every displayed comparison card a stable A/B/C label so
 * users can relate the decision card to the structure preview without changing
 * the underlying ranking authority.
 */
export function siteDisplayRank(site: Site, index: number): string {
  return site.rank?.trim() || String.fromCharCode(65 + index);
}

export function siteIdForOption(
  sites: Site[],
  decision: Decision | null | undefined,
  optionId: string | undefined,
): string | undefined {
  if (!optionId) return undefined;
  const direct = sites.find((site) => site.id === optionId);
  if (direct) return direct.id;
  const option = decision?.options.find((item) => item.option_id === optionId);
  if (!option) return undefined;
  if (option.rank) {
    const ranked = sites.find((site) => site.rank === option.rank);
    if (ranked) return ranked.id;
  }
  const index = decision?.options.findIndex((item) => item.option_id === optionId) ?? -1;
  return index >= 0 ? sites[index]?.id : undefined;
}

export function optionIdForSite(
  sites: Site[],
  decision: Decision | null | undefined,
  siteId: string,
): string | undefined {
  const direct = decision?.options.find((item) => item.option_id === siteId);
  if (direct) return direct.option_id;
  const index = sites.findIndex((site) => site.id === siteId);
  if (index < 0) return undefined;
  const site = sites[index];
  if (site.rank) {
    const ranked = decision?.options.find((item) => item.rank === site.rank);
    if (ranked) return ranked.option_id;
  }
  return decision?.options[index]?.option_id;
}
