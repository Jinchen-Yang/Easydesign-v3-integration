import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('pro');
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
      if (!response.ok) throw new Error(t('Resource service unavailable'));
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
    ? t('{{node}} compute node', {
        node: resources.node === 'Compute node' ? t('Compute node') : resources.node,
      })
    : resources?.connection === 'not-configured'
      ? t('No compute service connected')
      : resources?.connection === 'unavailable'
        ? t('{{node}} is unavailable', {
            node: resources.node === 'Compute node' ? t('Compute node') : resources.node,
          })
        : t('Connecting to compute node');
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
    <section className={`live-resources resource-${state}`} aria-label={t('Compute connection')}>
      <div className="resource-node">
        <span className="resource-node-icon">
          <Cpu size={24} />
        </span>
        <div className="resource-node-title">
          <span className="eyebrow">{t('GPU COMPUTE NODE')}</span>
          <h2>{title}</h2>
          <p>
            {sample
              ? t('Whole-node telemetry · Read-only · Refreshes every 10s')
              : resources?.connection === 'not-configured'
                ? t('Live resource monitoring is not configured on this device.')
                : resources?.connection === 'unavailable'
                  ? t('Could not reach the resource monitor. Retry in a moment.')
                  : t('Fetching hardware metrics…')}
          </p>
        </div>
        <div className="resource-node-actions">
          <span className={`resource-status ${state}`} role="status">
            <i />
            {live
              ? t('Live')
              : sample
                ? t('Stale data')
                : refreshing
                  ? t('Connecting')
                  : t('Not connected')}
          </span>
          <button
            className="secondary-button"
            disabled={refreshing}
            onClick={() => void refresh()}
            aria-label={t('Refresh resources')}
          >
            <RefreshCw size={13} className={refreshing ? 'resource-spin' : ''} />
            {refreshing ? t('Refreshing') : t('Refresh')}
          </button>
        </div>
      </div>
      {sample && (
        <>
          <div className="resource-summary">
            <div>
              <span>{t('Detected GPUs')}</span>
              <strong>
                {gpus.length}
                <small> {t('devices')}</small>
              </strong>
            </div>
            <div>
              <span>{t('Total memory')}</span>
              <strong>
                {display(sum('memoryTotalMiB'), '', 1)}
                <small> GiB</small>
              </strong>
            </div>
            <div>
              <span>{t('Used memory')}</span>
              <strong>
                {display(sum('memoryUsedMiB'), '', 1)}
                <small> GiB</small>
              </strong>
            </div>
            <div>
              <span>{t('Average utilization')}</span>
              <strong>
                {display(average, '%')}
                <small> GPU</small>
              </strong>
            </div>
          </div>
          <div className="resource-timestamp">
            <span>
              {t('Sampled')}{' '}
              <time dateTime={sample.sampledAt}>
                {new Date(sample.sampledAt).toLocaleTimeString('en-GB')}
              </time>{' '}
              · {age}
              {t('s ago')}
            </span>
            <span>
              {stale
                ? t('Connection delayed. These are the last known values.')
                : t('Includes activity outside EasyDesign.')}
            </span>
          </div>
          <div className="gpu-grid">
            {gpus.map((gpu) => (
              <article className="gpu-card" aria-label={`GPU ${gpu.index}`} key={gpu.index}>
                <header>
                  <span>GPU {gpu.index}</span>
                  <span className="gpu-load-label">
                    {gpu.utilization == null
                      ? t('Unknown')
                      : gpu.utilization >= 10
                        ? t('In use')
                        : t('Low utilization')}
                  </span>
                </header>
                <h3>{gpu.name.replace(/^NVIDIA /, '')}</h3>
                <div className="gpu-utilization">
                  <strong>{display(gpu.utilization, '%')}</strong>
                  <span>{t('utilization')}</span>
                </div>
                {gpu.utilization === null ? (
                  <div
                    className="gpu-metric-unavailable"
                    aria-label={t('Utilization unavailable')}
                  />
                ) : (
                  <progress
                    aria-label={t('GPU {{index}} utilization', {
                      index: gpu.index,
                    })}
                    max={100}
                    value={gpu.utilization}
                  />
                )}
                <div className="gpu-memory">
                  <span>{t('Memory')}</span>
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
                  <div
                    className="gpu-metric-unavailable"
                    aria-label={t('Memory usage unavailable')}
                  />
                ) : (
                  <progress
                    aria-label={t('GPU {{index}} memory', { index: gpu.index })}
                    max={gpu.memoryTotalMiB}
                    value={gpu.memoryUsedMiB}
                  />
                )}
                <dl>
                  <div>
                    <dt>{t('Temperature')}</dt>
                    <dd>{display(gpu.temperatureC, ' °C')}</dd>
                  </div>
                  <div>
                    <dt>{t('Power / limit')}</dt>
                    <dd>
                      {display(gpu.powerW)} / {display(gpu.powerLimitW, ' W')}
                    </dd>
                  </div>
                  <div>
                    <dt>{t('Compute processes')}</dt>
                    <dd>{display(gpu.processCount)}</dd>
                  </div>
                  <div>
                    <dt>{t('Driver')}</dt>
                    <dd>{gpu.driverVersion || '—'}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </>
      )}
      <p className="resource-queue-note">
        {t(
          'This panel shows hardware activity; it does not identify queued jobs or reserve capacity.',
        )}
      </p>
    </section>
  );
}
