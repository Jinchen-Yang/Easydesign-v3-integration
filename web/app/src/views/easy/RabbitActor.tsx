import type { CSSProperties } from 'react';
import { RabbitArt } from './RabbitArt';
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
/** The supplied rabbit remains the texture; gestures deform its original artwork. */
export function RabbitActor({ stage, active }: { stage: RabbitStage; active: boolean }) {
  return (
    <span className="rabbit-actor" aria-hidden="true" data-stage={stage}>
      <svg className="rabbit-scene rabbit-ground" viewBox="-100 -150 1454 1454" focusable="false">
        <ellipse
          className="bunny-shadow"
          cx="630"
          cy="1205"
          rx="365"
          ry="42"
          fill="#665b75"
          opacity=".13"
        />
      </svg>
      <span className="bunny-body">
        <RabbitArt stage={stage} active={active} />
        <svg className="rabbit-scene rabbit-props" viewBox="-100 -150 1454 1454" focusable="false">
          {stage === 'Target' && (
            <g className="bunny-magnifier" strokeLinecap="round">
              <path d="m465 682-90 155" stroke="#70513a" strokeWidth="57" />
              <path d="m465 682-90 155" stroke="#dcc6a0" strokeWidth="30" />
              <circle
                cx="524"
                cy="575"
                r="128"
                fill="#e8f9f8"
                fillOpacity=".62"
                stroke="#795e4f"
                strokeWidth="25"
              />
              <circle cx="524" cy="575" r="109" fill="none" stroke="#e9f7f7" strokeWidth="13" />
              <path
                d="M456 590q38-84 68 0t61-13m-105 53q21-52 50-5"
                stroke="#61a59b"
                strokeWidth="18"
                fill="none"
              />
            </g>
          )}
          {stage === 'Site' && (
            <g>
              <g className="bunny-site-map">
                <path
                  d="M1040 405q-125-90-160 39-109 26-40 133 70 68 145 5 129 6 120-79z"
                  fill="#e7f4ef"
                  stroke="#71a49b"
                  strokeWidth="12"
                />
                <circle cx="913" cy="468" r="20" fill="#b3a0ce" />
                <circle cx="990" cy="521" r="26" fill="#8060ad" />
                <circle
                  className="bunny-site-ring"
                  cx="990"
                  cy="521"
                  r="55"
                  fill="none"
                  stroke="#8060ad"
                  strokeWidth="10"
                />
              </g>
              <path
                className="bunny-pointer"
                d="m837 809 151-279"
                stroke="#766087"
                strokeWidth="26"
                strokeLinecap="round"
              />
            </g>
          )}
          {stage === 'Design' && (
            <g className="bunny-laptop" stroke="#7c6989" strokeWidth="12" strokeLinejoin="round">
              <path d="m277 862 589 0 56 269H327z" fill="#ebe6f2" />
              <path d="m327 1131 595 0 69 55H376z" fill="#cbc1df" />
              <path d="m317 895 515 0 36 194H355z" fill="#faf8fe" stroke="#c4b6d8" />
              <path
                className="bunny-code"
                d="m437 955-44 32 47 33m244-65 43 32-46 33m-104-85-23 105"
                fill="none"
                stroke="#9981b7"
                strokeWidth="16"
                strokeLinecap="round"
              />
            </g>
          )}
          {stage === 'Pilot' && (
            <g>
              <g className="bunny-pipette" stroke="#6d9695" strokeWidth="12" strokeLinejoin="round">
                <path d="m943 695 29-185h61l-36 190-39 84-23-7z" fill="#b7ded6" />
                <path d="m973 517 6-50h63l-8 53" fill="#c7b5df" />
                <path d="m991 473 3-25" strokeWidth="25" />
              </g>
              <path className="bunny-drop" d="M948 791q-42 68 0 69 42-1 0-69" fill="#74b7ad" />
              <path
                d="m917 893 0 177q32 43 64 0V893m-77 0h90"
                fill="#e5f6f2"
                stroke="#7aa69e"
                strokeWidth="13"
              />
              <path d="m930 1000 0 66q20 30 38 0v-66" fill="#92c9bc" />
            </g>
          )}
          {stage === 'Scale' && (
            <g className="bunny-rack" stroke="#89779d" strokeWidth="10">
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <g className="bunny-tube" key={i} style={{ '--tube': i } as CSSProperties}>
                  <path d={`M${300 + i * 120} 911v202q32 44 64 0V911Z`} fill="#f8f5fc" />
                  <path
                    className="bunny-liquid"
                    d={`M${315 + i * 120} 1005v101q16 24 34 0v-101z`}
                    fill={i % 2 ? '#b3a0d0' : '#8cc5b8'}
                    stroke="none"
                  />
                  <path d={`M${291 + i * 120} 911h82`} strokeLinecap="round" />
                </g>
              ))}
              <path d="M272 1117h730v51H272z" fill="#d7cce7" />
            </g>
          )}
        </svg>
      </span>
      <svg className="rabbit-scene rabbit-confetti" viewBox="-100 -150 1454 1454" focusable="false">
        {stage === 'Candidates' && (
          <g className="bunny-celebration" fill="#a28ac5">
            {[
              [120, 185],
              [1010, 135],
              [890, -40],
              [270, 5],
            ].map(([x, y], i) => (
              <path
                key={x}
                className="bunny-star"
                style={{ '--star': i } as CSSProperties}
                d={`M${x} ${y}l15 35 35 15-35 15-15 35-15-35-35-15 35-15z`}
              />
            ))}
          </g>
        )}
      </svg>
    </span>
  );
}
