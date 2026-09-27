import { describe, expect, it } from 'vitest';
import {limitDraftProblems} from '../src/accounts/AccountApp';
import type { QuotaLimits } from '../../shared/account-client';

const base: QuotaLimits = {
  max_active_jobs: 1, max_active_chats: 2, max_gpu_devices: 1,
  max_upload_bytes: 32 * 1024 ** 2, max_stored_upload_bytes: 10 * 1024 ** 3,
  max_candidates_per_job: 24,
};
const draft = (overrides: Partial<Record<keyof QuotaLimits, string>> = {}) =>
  Object.fromEntries(
    (Object.keys(base) as Array<keyof QuotaLimits>).map(key => [key, overrides[key] ?? String(base[key])]),
  ) as Record<keyof QuotaLimits, string>;

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
    expect(limitDraftProblems(draft({max_active_chats: '  '})).max_active_chats).toContain('不能为空');
    expect(limitDraftProblems(draft({max_active_jobs: '1.5'})).max_active_jobs).toBe('请输入有效整数。');
    expect(limitDraftProblems(draft({max_active_jobs: 'Infinity'})).max_active_jobs).toBe('请输入有效整数。');
  });
});
