import type { STEPS } from './contracts';

export type RabbitStage = 'Idle' | (typeof STEPS)[number];
export const RABBIT_ACTIONS: Record<RabbitStage, string> = {
  Idle: 'A little wave to get started',
  Target: 'Looking closely at the target',
  Site: 'Pointing out a binding site',
  Design: 'Sketching and typing a design',
  Pilot: 'Pipetting a small trial',
  Scale: 'Preparing a batch of samples',
  Candidates: 'Celebrating the candidate panel',
};

const ROOT = `${import.meta.env.BASE_URL}mascot/rabbit/originals/`;
export const RABBIT_STAGE_IMAGES: Record<RabbitStage, string> = {
  Idle: '01-welcome.jpg',
  Target: '02-discover.jpg',
  Site: '04-analyze.jpg',
  Design: '03-design.jpg',
  Pilot: '05-explore.jpg',
  Scale: '07-guide.jpg',
  Candidates: '06-easydesign.jpg',
};

export function rabbitStageImage(stage: RabbitStage) {
  return `${ROOT}${RABBIT_STAGE_IMAGES[stage]}`;
}

/** Each scientific stage uses the matching supplied DouDou illustration. */
export function RabbitActor({ stage, active }: { stage: RabbitStage; active: boolean }) {
  return (
    <span className="rabbit-actor" aria-hidden="true" data-stage={stage} data-active={active}>
      <span className="bunny-body">
        <img className="rabbit-stage-art" src={rabbitStageImage(stage)} alt="" draggable={false} />
      </span>
    </span>
  );
}
