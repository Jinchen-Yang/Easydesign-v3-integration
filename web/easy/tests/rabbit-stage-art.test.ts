import { describe, expect, it } from 'vitest';
import { RABBIT_STAGE_IMAGES, rabbitStageImage } from '../src/easy/RabbitActor';

describe('DouDou stage artwork', () => {
  it('uses a distinct supplied illustration at every workflow stage', () => {
    const images = Object.values(RABBIT_STAGE_IMAGES);
    expect(images).toHaveLength(7);
    expect(new Set(images).size).toBe(images.length);
    expect(rabbitStageImage('Pilot')).toContain('/mascot/rabbit/originals/05-explore.jpg');
    expect(rabbitStageImage('Candidates')).toContain('/mascot/rabbit/originals/06-easydesign.jpg');
  });
});
