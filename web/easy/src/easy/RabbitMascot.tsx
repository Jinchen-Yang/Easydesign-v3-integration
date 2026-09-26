import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { ArrowLeftRight, Images, Minus, Pause, Play, RotateCcw, Settings2, X } from 'lucide-react';
import { translate, type Locale } from './i18n';
import { RabbitActor, RABBIT_ACTIONS, type RabbitStage } from './RabbitActor';
import './rabbit-mascot.css';
import { RabbitChat } from './RabbitChat';
import type { ChatContext } from './chat';
import { rabbitChatLayout } from './rabbitChatLayout';

const visibleViewport = () => ({
  width: window.visualViewport?.width ?? innerWidth,
  height: window.visualViewport?.height ?? innerHeight,
  x: window.visualViewport?.offsetLeft ?? 0,
  y: window.visualViewport?.offsetTop ?? 0,
});

const ROOT = `${import.meta.env.BASE_URL}mascot/rabbit/`;
const PREFS_KEY = 'easydesign-rabbit-v1';
const PICTURES = [
  ['01-welcome', 'Welcome'],
  ['02-discover', 'Discover'],
  ['03-design', 'Design'],
  ['04-analyze', 'Analyze'],
  ['05-explore', 'Explore'],
  ['06-easydesign', 'EasyDesign'],
  ['07-guide', 'Guide'],
] as const;

type Position = { x: number; y: number };
type Preferences = {
  paused: boolean;
  minimized: boolean;
  side: 'left' | 'right';
  position: Position | null;
  allowMotion: boolean;
};
const bounded = (value: number, max = 1) => Math.max(0, Math.min(max, value));
function loadPreferences(): Preferences {
  try {
    const saved = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}');
    return {
      paused: saved?.paused === true,
      minimized: saved?.minimized === true,
      side: saved?.side === 'left' ? 'left' : 'right',
      position:
        Number.isFinite(saved?.position?.x) && Number.isFinite(saved?.position?.y)
          ? { x: bounded(saved.position.x), y: bounded(saved.position.y) }
          : null,
      allowMotion: saved?.allowMotion === true,
    };
  } catch {
    return { paused: false, minimized: false, side: 'right', position: null, allowMotion: false };
  }
}

// Chat receives a minimal page summary; the companion never invokes the design adapter.
export function RabbitMascot({
  locale,
  mood = 'idle',
  stage = 'Idle',
  chatContext = { stage, status: 'idle', goal: '' },
  chatEnabled = true,
}: {
  locale: Locale;
  mood?: 'idle' | 'running' | 'complete';
  stage?: RabbitStage;
  chatContext?: ChatContext;
  chatEnabled?: boolean;
}) {
  const t = (key: string) => translate(locale, key);
  const [prefs, setPrefs] = useState(loadPreferences);
  const [open, setOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatActivity, setChatActivity] = useState<'idle' | 'waiting' | 'replying'>('idle');
  const [gallery, setGallery] = useState(false);
  const [picture, setPicture] = useState(0);
  const [viewport, setViewport] = useState(() => ({ width: innerWidth, height: innerHeight }));
  const [chatViewport, setChatViewport] = useState(visibleViewport);
  const [dragPosition, setDragPosition] = useState<Position | null>(null);
  const [dragging, setDragging] = useState(false);
  const [menuHeight, setMenuHeight] = useState(370);
  const [hidden, setHidden] = useState(document.hidden);
  const [reducedMotion, setReducedMotion] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  const root = useRef<HTMLElement>(null);
  const pet = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const menu = useRef<HTMLElement>(null);
  const drag = useRef<{
    pointer: number;
    start: Position;
    origin: Position;
    latest: Position;
    moved: boolean;
  } | null>(null);
  const suppressClick = useRef(false);
  const systemPaused = reducedMotion && !prefs.allowMotion;
  const still = prefs.paused || systemPaused || hidden || dragging || prefs.minimized;
  const size = prefs.minimized ? 48 : viewport.width <= 740 ? 128 : 164;
  const margin = 12;
  const range = {
    x: Math.max(0, viewport.width - size - margin * 2),
    y: Math.max(0, viewport.height - size - margin * 2),
  };
  const position = dragPosition ?? prefs.position ?? { x: prefs.side === 'right' ? 1 : 0, y: 1 };
  const location = { x: margin + position.x * range.x, y: margin + position.y * range.y };
  const chatLayout = rabbitChatLayout(chatViewport, { ...location, size });
  const displayPet = chatOpen && !prefs.minimized ? chatLayout.pet : { ...location, size };
  const menuWidth = Math.min(280, viewport.width - margin * 2);
  const menuTop =
    location.y >= menuHeight + margin
      ? location.y - menuHeight - 8
      : Math.max(margin, Math.min(viewport.height - menuHeight - margin, location.y + size + 8));

  useEffect(() => {
    const visible = () => setChatViewport(visibleViewport());
    const resize = () => {
      setViewport({ width: innerWidth, height: innerHeight });
      visible();
    };
    window.addEventListener('resize', resize);
    window.visualViewport?.addEventListener('resize', visible);
    window.visualViewport?.addEventListener('scroll', visible);
    return () => {
      window.removeEventListener('resize', resize);
      window.visualViewport?.removeEventListener('resize', visible);
      window.visualViewport?.removeEventListener('scroll', visible);
    };
  }, []);
  useLayoutEffect(() => {
    if (open && menu.current) setMenuHeight(menu.current.getBoundingClientRect().height);
  }, [open, locale, viewport, systemPaused, prefs.paused]);

  useEffect(() => {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
    } catch {
      // The companion still works when local storage is unavailable.
    }
  }, [prefs]);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const motion = () => setReducedMotion(media.matches);
    const visibility = () => setHidden(document.hidden);
    media.addEventListener('change', motion);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      media.removeEventListener('change', motion);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, []);
  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLButtonElement>('.rabbit-popover button')?.focus();
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        pet.current?.focus();
      }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);
  useEffect(() => {
    if (gallery) dialog.current?.showModal();
    else dialog.current?.close();
  }, [gallery]);

  function minimize() {
    setChatOpen(false);
    setOpen(false);
    setPrefs((current) => ({ ...current, minimized: true }));
    requestAnimationFrame(() => pet.current?.focus());
  }
  function closeGallery() {
    setGallery(false);
    pet.current?.focus();
  }

  function startDrag(event: ReactPointerEvent<HTMLButtonElement>) {
    if (!event.isPrimary || event.button !== 0) return;
    suppressClick.current = false;
    drag.current = {
      pointer: event.pointerId,
      start: { x: event.clientX, y: event.clientY },
      origin: { x: displayPet.x, y: displayPet.y },
      latest: position,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function moveDrag(event: ReactPointerEvent<HTMLButtonElement>) {
    const current = drag.current;
    if (!current || current.pointer !== event.pointerId) return;
    const dx = event.clientX - current.start.x;
    const dy = event.clientY - current.start.y;
    if (!current.moved && Math.hypot(dx, dy) < 5) return;
    current.moved = true;
    suppressClick.current = true;
    current.latest = {
      x: bounded((current.origin.x + dx - margin) / (range.x || 1)),
      y: bounded((current.origin.y + dy - margin) / (range.y || 1)),
    };
    setOpen(false);
    setChatOpen(false);
    setDragging(true);
    setDragPosition(current.latest);
  }
  function endDrag(event: ReactPointerEvent<HTMLButtonElement>, cancelled = false) {
    const current = drag.current;
    if (!current || current.pointer !== event.pointerId) return;
    drag.current = null;
    if (current.moved && !cancelled) setPrefs((value) => ({ ...value, position: current.latest }));
    setDragPosition(null);
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
  }

  return (
    <>
      <aside
        ref={root}
        className={`rabbit-companion ${prefs.side} ${prefs.minimized ? 'minimized' : ''}`}
        style={{ left: displayPet.x, top: displayPet.y, width: displayPet.size }}
        aria-label={t('EasyDesign bunny')}
        data-motion={still ? 'paused' : 'playing'}
        data-mood={mood}
        data-stage={stage}
        data-dragging={dragging}
        data-chat={chatActivity}
        data-chat-compact={chatOpen && chatViewport.height < 500}
      >
        {chatEnabled && (
          <RabbitChat
            open={chatOpen && !prefs.minimized}
            locale={locale}
            context={chatContext}
            onActivity={setChatActivity}
            onClose={() => {
              setChatOpen(false);
              pet.current?.focus();
            }}
            onSettings={() => {
              setChatOpen(false);
              setOpen(true);
            }}
            style={chatLayout.panel}
          />
        )}
        {open && !prefs.minimized && (
          <section
            ref={menu}
            className="rabbit-popover"
            aria-label={t('Bunny controls')}
            style={{
              left: Math.max(
                margin,
                Math.min(viewport.width - menuWidth - margin, location.x + size - menuWidth),
              ),
              top: menuTop,
              width: menuWidth,
            }}
          >
            <div className="rabbit-popover-title">
              <strong>{t('Your little lab companion')}</strong>
              <button
                aria-label={t('Close bunny controls')}
                onClick={() => {
                  setOpen(false);
                  pet.current?.focus();
                }}
              >
                <X size={16} />
              </button>
            </div>
            <p>{t(RABBIT_ACTIONS[stage])}</p>
            <p className="rabbit-drag-hint" id="rabbit-drag-help">
              {t('Drag to move · Arrow keys also work')}
            </p>
            <div className="rabbit-actions">
              <button
                onClick={() =>
                  setPrefs((current) =>
                    systemPaused
                      ? { ...current, paused: false, allowMotion: true }
                      : { ...current, paused: !current.paused },
                  )
                }
              >
                {still ? <Play size={16} /> : <Pause size={16} />}
                {t(
                  systemPaused
                    ? 'Enable animation for bunny'
                    : prefs.paused
                      ? 'Resume animation'
                      : 'Pause animation',
                )}
              </button>
              {systemPaused && (
                <small className="rabbit-motion-note">
                  {t('System reduced motion is on. Play only if you prefer.')}
                </small>
              )}
              <button
                onClick={() =>
                  setPrefs((current) => ({
                    ...current,
                    side: current.side === 'right' ? 'left' : 'right',
                    position: { x: position.x >= 0.5 ? 0 : 1, y: position.y },
                  }))
                }
              >
                <ArrowLeftRight size={16} />
                {t('Move to other side')}
              </button>
              <button
                onClick={() =>
                  setPrefs((current) => ({ ...current, side: 'right', position: null }))
                }
              >
                <RotateCcw size={16} />
                {t('Reset bunny position')}
              </button>
              <button
                onClick={() => {
                  setOpen(false);
                  setGallery(true);
                }}
              >
                <Images size={16} />
                {t('Bunny album')}
              </button>
              <button onClick={minimize}>
                <Minus size={16} />
                {t('Minimize bunny')}
              </button>
            </div>
          </section>
        )}
        <button
          ref={pet}
          className="rabbit-pet"
          aria-label={t(prefs.minimized ? 'Show bunny' : 'Chat with bunny')}
          aria-expanded={!prefs.minimized && chatOpen}
          aria-description={t('Drag to move · Arrow keys also work')}
          title={t(prefs.minimized ? 'Show bunny' : 'Chat with bunny')}
          onPointerDown={startDrag}
          onPointerMove={moveDrag}
          onPointerUp={(event) => endDrag(event)}
          onPointerCancel={(event) => endDrag(event, true)}
          onLostPointerCapture={(event) => endDrag(event, true)}
          onKeyDown={(event) => {
            const directions: Record<string, Position> = {
              ArrowLeft: { x: -1, y: 0 },
              ArrowRight: { x: 1, y: 0 },
              ArrowUp: { x: 0, y: -1 },
              ArrowDown: { x: 0, y: 1 },
            };
            const direction = directions[event.key];
            if (!direction) return;
            event.preventDefault();
            const distance = event.shiftKey ? 40 : 20;
            setPrefs((current) => ({
              ...current,
              position: {
                x: bounded(position.x + (direction.x * distance) / (range.x || 1)),
                y: bounded(position.y + (direction.y * distance) / (range.y || 1)),
              },
            }));
          }}
          onClick={(event) => {
            if (suppressClick.current && event.detail !== 0) {
              suppressClick.current = false;
              return;
            }
            if (prefs.minimized) setPrefs((current) => ({ ...current, minimized: false }));
            else if (chatEnabled) {
              setOpen(false);
              setChatOpen((value) => !value);
            } else setOpen((value) => !value);
          }}
        >
          <RabbitActor stage={prefs.minimized ? 'Idle' : stage} active={!still} />
        </button>
        {!prefs.minimized && (
          <button
            className="rabbit-minimize rabbit-settings"
            aria-label={t('Bunny controls')}
            title={t('Bunny controls')}
            onClick={() => {
              setChatOpen(false);
              setOpen((value) => !value);
            }}
          >
            <Settings2 size={15} />
          </button>
        )}
        {!prefs.minimized && (
          <button
            className="rabbit-minimize"
            aria-label={t('Minimize bunny')}
            title={t('Minimize bunny')}
            onClick={minimize}
          >
            <Minus size={15} />
          </button>
        )}
      </aside>
      <dialog
        ref={dialog}
        className="rabbit-album"
        onCancel={closeGallery}
        onClick={(event) => {
          if (event.target === event.currentTarget) closeGallery();
        }}
        aria-labelledby="rabbit-album-title"
      >
        <header>
          <h2 id="rabbit-album-title">{t('Bunny album')}</h2>
          <button aria-label={t('Close album')} onClick={closeGallery}>
            <X size={20} />
          </button>
        </header>
        {gallery && (
          <>
            <img
              className="rabbit-album-main"
              src={`${ROOT}originals/${PICTURES[picture][0]}.jpg`}
              alt={t(PICTURES[picture][1])}
            />
            <div
              className="rabbit-thumbnails"
              role="group"
              aria-label={t('Choose a bunny picture')}
            >
              {PICTURES.map(([file, label], index) => (
                <button
                  key={file}
                  onClick={() => setPicture(index)}
                  aria-label={t(label)}
                  aria-pressed={index === picture}
                >
                  <img src={`${ROOT}originals/${file}.jpg`} alt="" loading="lazy" />
                </button>
              ))}
            </div>
            <footer>
              <span>
                {picture + 1} / {PICTURES.length}
              </span>
              <a href={`${ROOT}originals/${PICTURES[picture][0]}.jpg`} download>
                {t('Download original')}
              </a>
            </footer>
          </>
        )}
      </dialog>
    </>
  );
}
