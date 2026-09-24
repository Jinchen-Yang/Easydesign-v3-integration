import { useCallback, useEffect, useRef, useState } from 'react';
import { Cpu, RefreshCw } from 'lucide-react';
import {
  COMPUTE_ENDPOINT,
  REFRESH_MS,
  STALE_MS,
  parseComputeResources,
  type ComputeResources,
} from '../../domain/compute';
import '../../styles/compute.css';

const display = (value: number | null | undefined, suffix = '', digits = 0) =>
  value == null ? '—' : `${value.toFixed(digits)}${suffix}`;

export function LiveResources() {
  const [resources, setResources] = useState<ComputeResources | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [now, setNow] = useState(Date.now());
  const request = useRef<AbortController | null>(null);
  const mounted = useRef(false);
  const refresh = useCallback(async () => {
    if (request.current || !mounted.current) return;
    const controller = new AbortController();
    request.current = controller;
    setRefreshing(true);
    const timeout = window.setTimeout(() => controller.abort(), 14_000);
    try {
      const response = await fetch(COMPUTE_ENDPOINT, {
        signal: controller.signal,
        cache: 'no-store',
      });
      if (!response.ok) throw new Error('Resource service unavailable');
      const data = parseComputeResources(await response.json());
      if (mounted.current && request.current === controller) setResources(data);
    } catch {
      if (mounted.current && request.current === controller) {
        setResources((previous) => ({
          node: previous?.node ?? 'Compute node',
          sample: previous?.sample ?? null,
          connection: previous?.sample ? 'stale' : 'unavailable',
        }));
      }
    } finally {
      window.clearTimeout(timeout);
      if (request.current === controller) {
        request.current = null;
        if (mounted.current) {
          setRefreshing(false);
          setNow(Date.now());
        }
      }
    }
  }, []);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    const poll = window.setInterval(() => {
      if (!document.hidden) void refresh();
    }, REFRESH_MS);
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    const visible = () => {
      if (!document.hidden) {
        setNow(Date.now());
        void refresh();
      }
    };
    document.addEventListener('visibilitychange', visible);
    return () => {
      mounted.current = false;
      request.current?.abort();
      request.current = null;
      window.clearInterval(poll);
      window.clearInterval(clock);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [refresh]);

  const sample = resources?.sample;
  const age = sample ? Math.max(0, Math.floor((now - Date.parse(sample.sampledAt)) / 1000)) : null;
  const stale =
    resources?.connection === 'stale' || (sample && now - Date.parse(sample.sampledAt) > STALE_MS);
  const live = resources?.connection === 'connected' && !stale;
  const state = live ? 'live' : sample ? 'stale' : 'offline';
  const title = sample
    ? `${resources.node} compute node`
    : resources?.connection === 'not-configured'
      ? 'No compute service connected'
      : resources?.connection === 'unavailable'
        ? `${resources.node} is unavailable`
        : 'Connecting to compute node';
  const gpus = sample?.gpus ?? [];
  const sum = (key: 'memoryTotalMiB' | 'memoryUsedMiB') =>
    gpus.length && gpus.every((gpu) => gpu[key] !== null)
      ? gpus.reduce((n, gpu) => n + gpu[key]!, 0) / 1024
      : null;
  const average =
    gpus.length && gpus.every((gpu) => gpu.utilization !== null)
      ? gpus.reduce((n, gpu) => n + gpu.utilization!, 0) / gpus.length
      : null;
  return (
    <section className={`live-resources resource-${state}`} aria-label="Compute connection">
      <div className="resource-node">
        <span className="resource-node-icon">
          <Cpu size={24} />
        </span>
        <div className="resource-node-title">
          <span className="eyebrow">GPU COMPUTE NODE</span>
          <h2>{title}</h2>
          <p>
            {sample
              ? 'Whole-node telemetry · Read-only · Refreshes every 10s'
              : resources?.connection === 'not-configured'
                ? 'Live resource monitoring is not configured on this device.'
                : resources?.connection === 'unavailable'
                  ? 'Could not reach the resource monitor. Retry in a moment.'
                  : 'Fetching hardware metrics…'}
          </p>
        </div>
        <div className="resource-node-actions">
          <span className={`resource-status ${state}`} role="status">
            <i />
            {live ? 'Live' : sample ? 'Stale data' : refreshing ? 'Connecting' : 'Not connected'}
          </span>
          <button
            className="secondary-button"
            disabled={refreshing}
            onClick={() => void refresh()}
            aria-label="Refresh resources"
          >
            <RefreshCw size={13} className={refreshing ? 'resource-spin' : ''} />
            {refreshing ? 'Refreshing' : 'Refresh'}
          </button>
        </div>
      </div>
      {sample && (
        <>
          <div className="resource-summary">
            <div>
              <span>Detected GPUs</span>
              <strong>
                {gpus.length}
                <small> devices</small>
              </strong>
            </div>
            <div>
              <span>Total memory</span>
              <strong>
                {display(sum('memoryTotalMiB'), '', 1)}
                <small> GiB</small>
              </strong>
            </div>
            <div>
              <span>Used memory</span>
              <strong>
                {display(sum('memoryUsedMiB'), '', 1)}
                <small> GiB</small>
              </strong>
            </div>
            <div>
              <span>Average utilization</span>
              <strong>
                {display(average, '%')}
                <small> GPU</small>
              </strong>
            </div>
          </div>
          <div className="resource-timestamp">
            <span>
              Sampled{' '}
              <time dateTime={sample.sampledAt}>
                {new Date(sample.sampledAt).toLocaleTimeString('en-GB')}
              </time>{' '}
              · {age}s ago
            </span>
            <span>
              {stale
                ? 'Connection delayed. These are the last known values.'
                : 'Includes activity outside EasyDesign.'}
            </span>
          </div>
          <div className="gpu-grid">
            {gpus.map((gpu) => (
              <article className="gpu-card" aria-label={`GPU ${gpu.index}`} key={gpu.index}>
                <header>
                  <span>GPU {gpu.index}</span>
                  <span className="gpu-load-label">
                    {gpu.utilization == null
                      ? 'Unknown'
                      : gpu.utilization >= 10
                        ? 'In use'
                        : 'Low utilization'}
                  </span>
                </header>
                <h3>{gpu.name.replace(/^NVIDIA /, '')}</h3>
                <div className="gpu-utilization">
                  <strong>{display(gpu.utilization, '%')}</strong>
                  <span>utilization</span>
                </div>
                {gpu.utilization === null ? (
                  <div className="gpu-metric-unavailable" aria-label="Utilization unavailable" />
                ) : (
                  <progress
                    aria-label={`GPU ${gpu.index} utilization`}
                    max={100}
                    value={gpu.utilization}
                  />
                )}
                <div className="gpu-memory">
                  <span>Memory</span>
                  <span>
                    {display(gpu.memoryUsedMiB == null ? null : gpu.memoryUsedMiB / 1024, '', 1)} /{' '}
                    {display(
                      gpu.memoryTotalMiB == null ? null : gpu.memoryTotalMiB / 1024,
                      ' GiB',
                      1,
                    )}
                  </span>
                </div>
                {gpu.memoryUsedMiB === null || !gpu.memoryTotalMiB ? (
                  <div className="gpu-metric-unavailable" aria-label="Memory usage unavailable" />
                ) : (
                  <progress
                    aria-label={`GPU ${gpu.index} memory`}
                    max={gpu.memoryTotalMiB}
                    value={gpu.memoryUsedMiB}
                  />
                )}
                <dl>
                  <div>
                    <dt>Temperature</dt>
                    <dd>{display(gpu.temperatureC, ' °C')}</dd>
                  </div>
                  <div>
                    <dt>Power / limit</dt>
                    <dd>
                      {display(gpu.powerW)} / {display(gpu.powerLimitW, ' W')}
                    </dd>
                  </div>
                  <div>
                    <dt>Compute processes</dt>
                    <dd>{display(gpu.processCount)}</dd>
                  </div>
                  <div>
                    <dt>Driver</dt>
                    <dd>{gpu.driverVersion || '—'}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </>
      )}
      <p className="resource-queue-note">
        Job queue not connected. GPU activity does not identify queued jobs or reserve capacity.
      </p>
    </section>
  );
}
