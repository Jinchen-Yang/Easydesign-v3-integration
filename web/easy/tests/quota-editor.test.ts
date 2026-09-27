import { describe, expect, it } from 'vitest';
import {limitDraftProblems, limitPayloadFromDraft} from '../src/accounts/AccountApp';
import type { QuotaLimits } from '../../shared/account-client';

const base: QuotaLimits = {
  max_active_jobs: 1, max_active_chats: 2, max_gpu_devices: 1,
  max_upload_bytes: 32 * 1024 ** 2, max_stored_upload_bytes: 10 * 1024 ** 3,
  max_candidates_per_job: 24,
  final_designs_allowance: 30, pilot_stage_budget: 30, scale_stage_budget: 30,
};

const draft = (
  required: Partial<Record<string, string>> = {},
  nullable: Partial<Record<string, {unlimited: boolean; text: string}>> = {},
) => ({
  max_active_jobs: required.max_active_jobs ?? String(base.max_active_jobs),
  max_active_chats: required.max_active_chats ?? String(base.max_active_chats),
  max_gpu_devices: required.max_gpu_devices ?? String(base.max_gpu_devices),
  max_upload_bytes: required.max_upload_bytes ?? String(base.max_upload_bytes),
  max_stored_upload_bytes: required.max_stored_upload_bytes ?? String(base.max_stored_upload_bytes),
  max_candidates_per_job: required.max_candidates_per_job ?? String(base.max_candidates_per_job),
  final_designs_allowance: nullable.final_designs_allowance ?? {unlimited: false, text: '30'},
  pilot_stage_budget: nullable.pilot_stage_budget ?? {unlimited: false, text: '30'},
  scale_stage_budget: nullable.scale_stage_budget ?? {unlimited: false, text: '30'},
});

describe('quota editor field validation mirrors the backend schema', () => {
  it('accepts the schema minima and maxima', () => {
    const edges = draft({
      max_active_jobs: '0',
      max_active_chats: '64',
      max_gpu_devices: '1',
      max_upload_bytes: '1024',
      max_stored_upload_bytes: String(10 * 1024 ** 4),
      max_candidates_per_job: '1000000',
    });
    expect(limitDraftProblems(edges)).toEqual({});
    expect(limitDraftProblems(draft())).toEqual({});
  });
  it('rejects values the backend ResourceLimits would refuse, per field', () => {
    const problems = limitDraftProblems(draft({
      max_gpu_devices: '0',
      max_upload_bytes: '1023',
      max_stored_upload_bytes: String(10 * 1024 ** 4 + 1),
      max_candidates_per_job: '0',
      max_active_jobs: '65',
    }));
    expect(problems.max_gpu_devices).toContain('必须在 1 到 64 之间');
    expect(problems.max_upload_bytes).toContain('必须在 1024 到');
    expect(problems.max_stored_upload_bytes).toContain('必须在 1024 到');
    expect(problems.max_candidates_per_job).toContain('必须在 1 到 1000000 之间');
    expect(problems.max_active_jobs).toContain('必须在 0 到 64 之间');
  });
  it('demands a useful message for empty or non-finite input instead of sending null/zero', () => {
    expect(limitDraftProblems(draft({max_gpu_devices: ''})).max_gpu_devices).toContain('不能为空');
    expect(limitDraftProblems(draft({'max_active_chats': '  '})).max_active_chats).toContain('不能为空');
    expect(limitDraftProblems(draft({max_active_jobs: '1.5'})).max_active_jobs).toBe('请输入有效整数。');
    expect(limitDraftProblems(draft({max_active_jobs: 'Infinity'})).max_active_jobs).toBe('请输入有效整数。');
  });
});

describe('nullable quota fields keep null an explicit choice', () => {
  it('validates the new cumulative allowance and stage budget ranges', () => {
    expect(limitDraftProblems(draft({}, {
      final_designs_allowance: {unlimited: false, text: '0'},
      pilot_stage_budget: {unlimited: false, text: '10000'},
      scale_stage_budget: {unlimited: false, text: '1'},
    }))).toEqual({});
    const problems = limitDraftProblems(draft({}, {
      final_designs_allowance: {unlimited: false, text: '1000001'},
      pilot_stage_budget: {unlimited: false, text: '0'},
      scale_stage_budget: {unlimited: false, text: '10001'},
    }));
    expect(problems.final_designs_allowance).toContain('必须在 0 到 1000000 之间');
    expect(problems.pilot_stage_budget).toContain('必须在 1 到 10000 之间');
    expect(problems.scale_stage_budget).toContain('必须在 1 到 10000 之间');
  });
  it('treats the unlimited toggle as the explicit null meaning, never as an empty number', () => {
    expect(limitDraftProblems(draft({}, {
      final_designs_allowance: {unlimited: true, text: ''},
      pilot_stage_budget: {unlimited: true, text: ''},
      scale_stage_budget: {unlimited: true, text: ''},
    }))).toEqual({});
    // Unchecking without typing a number is invalid and must say how to fix it.
    const empty = limitDraftProblems(draft({}, {final_designs_allowance: {unlimited: false, text: ''}}));
    expect(empty.final_designs_allowance).toContain('不能为空');
    expect(empty.final_designs_allowance).toContain('不限制（不启用余额检查）');
    const stage = limitDraftProblems(draft({}, {scale_stage_budget: {unlimited: false, text: '  '}}));
    expect(stage.scale_stage_budget).toContain('使用原生默认');
    expect(limitDraftProblems(draft({}, {pilot_stage_budget: {unlimited: false, text: '30.5'}})).pilot_stage_budget)
      .toBe('请输入有效整数。');
  });
  it('submits null exactly for unlimited fields and numbers otherwise', () => {
    expect(limitPayloadFromDraft(draft({}, {
      final_designs_allowance: {unlimited: true, text: ''},
      pilot_stage_budget: {unlimited: false, text: '42'},
      scale_stage_budget: {unlimited: true, text: ''},
    }))).toEqual({...base, final_designs_allowance: null, pilot_stage_budget: 42, scale_stage_budget: null});
    expect(limitPayloadFromDraft(draft())).toEqual(base);
  });
});
