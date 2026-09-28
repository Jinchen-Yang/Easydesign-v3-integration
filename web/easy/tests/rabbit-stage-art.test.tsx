import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { RabbitActor } from '../src/easy/RabbitActor';

describe('DouDou stage artwork', () => {
  it('keeps the transparent mascot and adds distinct task props for scientific stages', () => {
    const target = renderToStaticMarkup(<RabbitActor stage="Target" active />);
    const site = renderToStaticMarkup(<RabbitActor stage="Site" active />);
    const design = renderToStaticMarkup(<RabbitActor stage="Design" active />);
    const pilot = renderToStaticMarkup(<RabbitActor stage="Pilot" active />);
    const scale = renderToStaticMarkup(<RabbitActor stage="Scale" active />);
    const candidates = renderToStaticMarkup(<RabbitActor stage="Candidates" active />);

    expect(target).toContain('bunny-magnifier');
    expect(site).toContain('bunny-site-map');
    expect(design).toContain('bunny-laptop');
    expect(pilot).toContain('bunny-pipette');
    expect(scale).toContain('bunny-rack');
    expect(candidates).toContain('bunny-celebration');

    for (const stage of [target, site, design, pilot, scale, candidates]) {
      expect(stage).toContain('rabbit-mesh');
      expect(stage).not.toContain('/originals/');
    }
  });
});
