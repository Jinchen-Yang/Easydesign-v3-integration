import { describe, it, expect, vi } from 'vitest';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { createResourceMonitor, resourceMiddleware, sshArgs } from '../server/compute';
import {
  parseResourceSample,
  REFRESH_MS,
  STALE_MS,
  type ResourceSample,
} from '../src/domain/compute';

const at = Date.parse('2026-09-19T12:00:00Z');
function sample(time = at): ResourceSample {
  return {
    sampledAt: new Date(time).toISOString(),
    gpus: [
      {
        index: 0,
        name: 'NVIDIA A100-PCIE-40GB',
        driverVersion: '580.173.02',
        utilization: 97,
        memoryTotalMiB: 40960,
        memoryUsedMiB: 11417,
        temperatureC: 60,
        powerW: 250.32,
        powerLimitW: 250,
        processCount: 1,
      },
    ],
  };
}
describe('read-only compute monitor', () => {
  it('coalesces concurrent refreshes and caches samples without changing sample time', async () => {
    let now = at;
    let release!: (s: ResourceSample) => void;
    const collect = vi.fn(
      () =>
        new Promise<ResourceSample>((resolve) => {
          release = resolve;
        }),
    );
    const monitor = createResourceMonitor('Suzhou2', collect, () => now);
    const a = monitor(),
      b = monitor();
    expect(collect).toHaveBeenCalledTimes(1);
    release(sample());
    expect((await a).connection).toBe('connected');
    expect(await b).toEqual(await a);
    now += REFRESH_MS - 1;
    expect((await monitor()).sample?.sampledAt).toBe(sample().sampledAt);
    expect(collect).toHaveBeenCalledTimes(1);
  });
  it('marks failed refreshes stale, retains actual values, and recovers on a new sample', async () => {
    let now = at;
    const collect = vi
      .fn()
      .mockResolvedValueOnce(sample())
      .mockRejectedValueOnce(new Error('SSH secret diagnostics'))
      .mockImplementation(() => Promise.resolve(sample(now)));
    const monitor = createResourceMonitor('Suzhou2', collect, () => now);
    await monitor();
    now += REFRESH_MS;
    const stale = await monitor();
    expect(stale.connection).toBe('stale');
    expect(stale.sample).toEqual(sample());
    expect(JSON.stringify(stale)).not.toContain('secret');
    now += REFRESH_MS;
    expect((await monitor()).connection).toBe('connected');
  });
  it('does not invent GPUs when disabled, disconnected, malformed or out of date', async () => {
    const collect = vi.fn().mockRejectedValue(new Error('offline'));
    expect((await createResourceMonitor('', collect)()).connection).toBe('not-configured');
    expect(collect).not.toHaveBeenCalled();
    expect(await createResourceMonitor('Suzhou2', collect)()).toMatchObject({
      connection: 'unavailable',
      sample: null,
    });
    for (const bad of [sample(at - STALE_MS - 1), sample(at + 60_000), { ...sample(), gpus: [] }]) {
      expect(
        (
          await createResourceMonitor(
            'Suzhou2',
            async () => bad,
            () => at,
          )()
        ).connection,
      ).toBe('unavailable');
    }
  });
  it('preserves N/A and rejects invalid identities, duplicate GPUs and impossible utilization', () => {
    const data = sample();
    data.gpus[0].powerW = null;
    expect(parseResourceSample(data).gpus[0].powerW).toBeNull();
    expect(() => parseResourceSample({ ...data, gpus: [...data.gpus, ...data.gpus] })).toThrow();
    data.gpus[0].utilization = 101;
    expect(() => parseResourceSample(data)).toThrow();
  });
  it('uses a fixed SSH command and refuses host argument injection', () => {
    for (const value of [
      '-oProxyCommand=bad',
      'Suzhou2; touch /tmp/bad',
      'user@host',
      'host\ncommand',
    ])
      expect(() => sshArgs(value)).toThrow();
    expect(sshArgs('Suzhou2')).toContain('StrictHostKeyChecking=yes');
    expect(sshArgs('Suzhou2')).toContain('ClearAllForwardings=yes');
    expect(sshArgs('Suzhou2').at(-1)).toContain('nvidia-smi');
  });
  it('accepts only same-origin, local GET without query parameters', async () => {
    const monitor = vi.fn(async () => ({
      connection: 'not-configured' as const,
      node: 'Compute node',
      sample: null,
    }));
    const middleware = resourceMiddleware(monitor);
    for (const [method, url, host, origin, status] of [
      ['POST', '/api/compute/resources', '127.0.0.1:13180', undefined, 405],
      ['GET', '/api/compute/resources?host=elsewhere', '127.0.0.1:13180', undefined, 400],
      ['GET', '/api/compute/resources', 'evil.example', undefined, 403],
      ['GET', '/api/compute/resources', '127.0.0.1:13180', 'https://evil.example', 403],
    ] as const) {
      const res = { setHeader: vi.fn(), end: vi.fn(), statusCode: 200 };
      await middleware(
        { method, url, headers: { host, origin } } as IncomingMessage,
        res as unknown as ServerResponse,
        vi.fn(),
      );
      expect(res.statusCode).toBe(status);
    }
    expect(monitor).not.toHaveBeenCalled();
    const res = { setHeader: vi.fn(), end: vi.fn(), statusCode: 200 };
    await middleware(
      {
        method: 'GET',
        url: '/api/compute/resources',
        headers: { host: '127.0.0.1:13180', origin: 'http://127.0.0.1:13180' },
      } as IncomingMessage,
      res as unknown as ServerResponse,
      vi.fn(),
    );
    expect(monitor).toHaveBeenCalledTimes(1);
    expect(res.setHeader).toHaveBeenCalledWith('Cache-Control', 'no-store');
  });
});
