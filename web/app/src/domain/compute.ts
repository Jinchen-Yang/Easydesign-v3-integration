export const COMPUTE_ENDPOINT = '/api/compute/resources';
export const REFRESH_MS = 10_000;
export const STALE_MS = 25_000;

export interface GpuResource {
  index: number;
  name: string;
  utilization: number | null;
  memoryTotalMiB: number | null;
  memoryUsedMiB: number | null;
  temperatureC: number | null;
  powerW: number | null;
  powerLimitW: number | null;
  processCount: number | null;
  driverVersion: string;
}
export interface ResourceSample {
  sampledAt: string;
  gpus: GpuResource[];
}
export interface ComputeResources {
  connection: 'connected' | 'stale' | 'unavailable' | 'not-configured';
  node: string;
  sample: ResourceSample | null;
}

/** Reject invalid telemetry rather than displaying missing values as zero. */
export function parseResourceSample(input: unknown): ResourceSample {
  if (!input || typeof input !== 'object') throw new Error('Invalid resource sample');
  const value = input as ResourceSample;
  if (
    typeof value.sampledAt !== 'string' ||
    !Number.isFinite(Date.parse(value.sampledAt)) ||
    !Array.isArray(value.gpus) ||
    !value.gpus.length ||
    value.gpus.length > 128
  )
    throw new Error('Invalid resource sample');
  const ids = new Set<number>();
  const metric = (n: unknown, max = 1e9): number | null => {
    if (n === null) return null;
    if (typeof n !== 'number' || !Number.isFinite(n) || n < 0 || n > max)
      throw new Error('Invalid GPU metric');
    return n;
  };
  const gpus = value.gpus.map((gpu) => {
    if (
      !gpu ||
      !Number.isInteger(gpu.index) ||
      gpu.index < 0 ||
      ids.has(gpu.index) ||
      typeof gpu.name !== 'string' ||
      !gpu.name.trim() ||
      gpu.name.length > 160 ||
      typeof gpu.driverVersion !== 'string' ||
      gpu.driverVersion.length > 80
    )
      throw new Error('Invalid GPU identity');
    ids.add(gpu.index);
    const processCount = metric(gpu.processCount);
    if (processCount !== null && !Number.isInteger(processCount)) throw new Error('Invalid count');
    return {
      index: gpu.index,
      name: gpu.name,
      driverVersion: gpu.driverVersion,
      utilization: metric(gpu.utilization, 100),
      memoryTotalMiB: metric(gpu.memoryTotalMiB),
      memoryUsedMiB: metric(gpu.memoryUsedMiB),
      temperatureC: metric(gpu.temperatureC, 200),
      powerW: metric(gpu.powerW),
      powerLimitW: metric(gpu.powerLimitW),
      processCount,
    };
  });
  return { sampledAt: value.sampledAt, gpus };
}

export function parseComputeResources(input: unknown): ComputeResources {
  if (!input || typeof input !== 'object') throw new Error('Invalid compute response');
  const value = input as ComputeResources;
  if (
    !['connected', 'stale', 'unavailable', 'not-configured'].includes(value.connection) ||
    typeof value.node !== 'string' ||
    value.node.length > 100
  )
    throw new Error('Invalid compute response');
  const sample = value.sample === null ? null : parseResourceSample(value.sample);
  if ((value.connection === 'connected' || value.connection === 'stale') && !sample)
    throw new Error('Missing telemetry');
  if ((value.connection === 'unavailable' || value.connection === 'not-configured') && sample)
    throw new Error('Unexpected telemetry');
  return { connection: value.connection, node: value.node, sample };
}
