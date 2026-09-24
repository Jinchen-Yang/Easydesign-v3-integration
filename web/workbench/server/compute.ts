import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Plugin } from 'vite';
import {
  COMPUTE_ENDPOINT,
  REFRESH_MS,
  STALE_MS,
  parseResourceSample,
  type ComputeResources,
  type ResourceSample,
} from '../src/domain/compute';

// Fixed read-only command. The browser cannot supply commands, hosts or paths.
const COLLECTOR = `import csv,io,json,subprocess
def query(fields,kind='gpu'):
 return subprocess.check_output(['nvidia-smi','--query-'+kind+'='+fields,'--format=csv,noheader,nounits'],text=True,timeout=5)
def number(value):
 try: return float(value.strip())
 except ValueError: return None
rows=list(csv.reader(io.StringIO(query('index,name,uuid,utilization.gpu,memory.total,memory.used,temperature.gpu,power.draw,power.limit,driver_version'))))
counts=None
try:
 process_rows=list(csv.reader(io.StringIO(query('gpu_uuid,pid','compute-apps'))))
 counts={}
 for uuid,pid in process_rows:
  counts.setdefault(uuid.strip(),set()).add(pid.strip())
except (subprocess.SubprocessError,ValueError): counts=None
gpus=[]
for row in rows:
 index,name,uuid,util,total,used,temp,power,limit,driver=[v.strip() for v in row]
 gpus.append(dict(index=int(index),name=name,utilization=number(util),memoryTotalMiB=number(total),memoryUsedMiB=number(used),temperatureC=number(temp),powerW=number(power),powerLimitW=number(limit),processCount=len(counts.get(uuid,set())) if counts is not None else None,driverVersion=driver))
print(json.dumps(dict(gpus=gpus)))`;

export function sshArgs(host: string): string[] {
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/.test(host)) throw new Error('Invalid SSH host alias');
  const quote = (value: string) => "'" + value.replaceAll("'", "'\\''") + "'";
  return [
    '-T',
    '-o',
    'BatchMode=yes',
    '-o',
    'ClearAllForwardings=yes',
    '-o',
    'StrictHostKeyChecking=yes',
    '-o',
    'ConnectTimeout=5',
    '-o',
    'ConnectionAttempts=1',
    '-o',
    'ServerAliveInterval=3',
    '-o',
    'ServerAliveCountMax=2',
    host,
    'python3 -c ' + quote(COLLECTOR),
  ];
}

export async function collectResources(host: string): Promise<ResourceSample> {
  const { stdout } = await promisify(execFile)('ssh', sshArgs(host), {
    timeout: 12_000,
    killSignal: 'SIGKILL',
    maxBuffer: 256 * 1024,
    encoding: 'utf8',
  });
  // Freshness uses the collector's receipt clock, not the GPU host's potentially skewed clock.
  return parseResourceSample({ ...JSON.parse(stdout), sampledAt: new Date().toISOString() });
}

/** A short-lived telemetry cache, with one in-flight sample; never a job scheduler. */
export function createResourceMonitor(host: string, collect = collectResources, now = Date.now) {
  if (host) sshArgs(host);
  let last: ResourceSample | null = null;
  let checkedAt = -Infinity;
  let failed = false;
  let pending: Promise<void> | undefined;
  return async (): Promise<ComputeResources> => {
    if (!host) return { connection: 'not-configured', node: 'Compute node', sample: null };
    if (!pending && now() - checkedAt >= REFRESH_MS) {
      pending = (async () => {
        try {
          const sample = parseResourceSample(await collect(host));
          const age = now() - Date.parse(sample.sampledAt);
          if (age < -5000 || age > STALE_MS) throw new Error('Stale or invalid sample clock');
          last = sample;
          failed = false;
        } catch {
          // Do not expose SSH diagnostics, credentials, usernames, paths or process commands.
          failed = true;
        } finally {
          checkedAt = now();
        }
      })();
    }
    if (pending) {
      await pending;
      pending = undefined;
    }
    const stale = failed || (last !== null && now() - Date.parse(last.sampledAt) > STALE_MS);
    return {
      node: host,
      connection: last ? (stale ? 'stale' : 'connected') : 'unavailable',
      sample: last,
    };
  };
}

/** Local same-origin GET only. No browser-controlled SSH or job execution surface. */
export function resourceMiddleware(monitor: () => Promise<ComputeResources>) {
  return async (req: IncomingMessage, res: ServerResponse, next: () => void) => {
    if (req.url?.split('?')[0] !== COMPUTE_ENDPOINT) return next();
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    const reject = (code: number) => {
      res.statusCode = code;
      res.end(JSON.stringify({ error: 'Request not allowed' }));
    };
    const host = req.headers.host ?? '';
    if (
      !/^(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$/.test(host) ||
      (req.headers.origin && req.headers.origin !== 'http://' + host) ||
      req.headers['sec-fetch-site'] === 'cross-site'
    )
      return reject(403);
    if (req.method !== 'GET') {
      res.setHeader('Allow', 'GET');
      return reject(405);
    }
    if (req.url !== COMPUTE_ENDPOINT) return reject(400);
    res.end(JSON.stringify(await monitor()));
  };
}

export function computePlugin(host: string): Plugin {
  const middleware = resourceMiddleware(createResourceMonitor(host));
  return {
    name: 'easydesign-readonly-compute',
    configureServer(server) {
      server.middlewares.use(middleware);
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware);
    },
  };
}
