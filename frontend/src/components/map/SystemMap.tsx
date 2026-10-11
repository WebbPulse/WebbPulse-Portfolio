import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import type { PublicFigure } from '../../services/api';
import {
  MAP_EDGES,
  MAP_NODES,
  MAP_TIERS,
  MAP_VIEWBOX,
  NODE_HALF,
  connectedTo,
  edgeGeometry,
  edgeTouches,
  findNode,
  nearestInDirection,
  nodeDescription,
  type MapDirection,
  type MapNode,
} from '../../content/map';
import { useReducedMotion } from '../../hooks';
import { LiveDot } from '../drawing';
import { figureValue } from './figures';
import { useCaseStudyTransition } from './useCaseStudyTransition';

/** Props for {@link SystemMap}. */
interface SystemMapProps {
  figures: Map<string, PublicFigure>;
}

/** The arrow keys and the direction each one moves. */
const ARROWS: Record<string, MapDirection> = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  ArrowLeft: 'left',
  ArrowRight: 'right',
};

/** A percentage of the map's width. */
const pctX = (x: number): string => `${(x / MAP_VIEWBOX.width) * 100}%`;

/** A percentage of the map's height. */
const pctY = (y: number): string => `${(y / MAP_VIEWBOX.height) * 100}%`;

/** The live figure line inside a node, or nothing when there is none. */
const NodeFigure: React.FC<{ figure: PublicFigure | undefined }> = ({
  figure,
}) =>
  figure ? (
    <span className="flex items-center gap-1.5 font-mono text-xs text-live-ink">
      <LiveDot className="h-1.5 w-1.5" />
      {figureValue(figure)}
    </span>
  ) : null;

/** The lines a node shows: kind, label and facts. */
const NodeBody: React.FC<{
  node: MapNode;
  figure: PublicFigure | undefined;
}> = ({ node, figure }) => (
  <>
    <span className="flex items-center justify-between gap-2">
      <span className="mono-label truncate">{node.kind}</span>
      <NodeFigure figure={figure} />
    </span>
    <span className="block truncate text-[0.9375rem] font-semibold tracking-tight text-ink">
      {node.label}
    </span>
    <span className="block truncate font-mono text-xs text-ink-muted">
      {node.facts.slice(0, 2).join(' · ')}
    </span>
  </>
);

/**
 * The interactive drawing of the WebbPulse estate: products over shared
 * packages over the AWS organisation, with every real connection drawn.
 *
 * Hover or focus lights a node and its connections. Arrow keys move between
 * nodes by position, Home and End jump to the ends, and Enter opens the case
 * study. Below the `lg` breakpoint the same data renders as a vertical list.
 */
export const SystemMap: React.FC<SystemMapProps> = ({ figures }) => {
  const location = useLocation();
  const reduced = useReducedMotion();
  const openCaseStudy = useCaseStudyTransition(reduced);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string>(MAP_NODES[0]?.id ?? '');
  const nodeRefs = useRef(new Map<string, HTMLElement>());
  const itemRefs = useRef(new Map<string, HTMLElement>());

  const connected = useMemo(
    () => new Set(activeId ? connectedTo(activeId) : []),
    [activeId]
  );

  const focusNodeState = (location.state as { focusNode?: unknown } | null)
    ?.focusNode;
  const focusTarget = typeof focusNodeState === 'string' ? focusNodeState : '';

  useEffect(() => {
    if (!focusTarget) return;
    const onMap = nodeRefs.current.get(focusTarget);
    const inList = itemRefs.current.get(focusTarget);
    const target = onMap && onMap.offsetParent !== null ? onMap : inList;
    if (!target) return;
    target.scrollIntoView?.({
      block: 'center',
      behavior: reduced ? 'auto' : 'smooth',
    });
    target.focus({ preventScroll: true });
  }, [focusTarget, location.key, reduced]);

  const moveFocus = (id: string | undefined) => {
    if (!id) return;
    nodeRefs.current.get(id)?.focus();
  };

  const onNodeKeyDown = (event: React.KeyboardEvent, node: MapNode) => {
    const direction = ARROWS[event.key];
    if (direction) {
      event.preventDefault();
      moveFocus(nearestInDirection(node.id, direction)?.id);
    } else if (event.key === 'Home') {
      event.preventDefault();
      moveFocus(MAP_NODES[0]?.id);
    } else if (event.key === 'End') {
      event.preventDefault();
      moveFocus(MAP_NODES[MAP_NODES.length - 1]?.id);
    } else if (event.key === 'Escape') {
      setActiveId(null);
    }
  };

  const nodeState = (id: string): 'active' | 'linked' | 'dim' | 'idle' => {
    if (!activeId) return 'idle';
    if (id === activeId) return 'active';
    return connected.has(id) ? 'linked' : 'dim';
  };

  return (
    <div>
      <div
        className="system-map relative hidden lg:block"
        role="group"
        aria-label="System map of the WebbPulse estate"
        aria-describedby="system-map-help"
        onMouseLeave={() => setActiveId(null)}
      >
        <p id="system-map-help" className="sr-only">
          Use the arrow keys to move between parts of the system, and Enter to
          open a case study.
        </p>
        <svg
          className="absolute inset-0 h-full w-full overflow-visible"
          viewBox={`0 0 ${MAP_VIEWBOX.width} ${MAP_VIEWBOX.height}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {MAP_TIERS.map((tier) => (
            <g key={tier.id} className="map-tier">
              <line
                x1="0"
                x2={MAP_VIEWBOX.width}
                y1={tier.y - 70}
                y2={tier.y - 70}
              />
            </g>
          ))}
          <rect
            className="map-boundary"
            x="150"
            y="450"
            width="700"
            height="120"
          />
          {MAP_EDGES.map((edge) => {
            const from = findNode(edge.from);
            const to = findNode(edge.to);
            if (!from || !to) return null;
            const geometry = edgeGeometry(from, to);
            const state = !activeId
              ? 'idle'
              : edgeTouches(edge, activeId)
                ? 'active'
                : 'dim';
            return (
              <g key={`${edge.from}-${edge.to}`} data-state={state}>
                <path
                  className="map-edge"
                  d={geometry.path}
                  pathLength={1}
                  data-state={state}
                />
                <circle
                  className="map-pin"
                  cx={geometry.start[0]}
                  cy={geometry.start[1]}
                  r="2.5"
                />
                <circle
                  className="map-pin"
                  cx={geometry.end[0]}
                  cy={geometry.end[1]}
                  r="2.5"
                />
              </g>
            );
          })}
        </svg>

        {MAP_TIERS.map((tier) => (
          <span
            key={tier.id}
            className="mono-label pointer-events-none absolute left-0 -translate-y-full pb-1"
            style={{ top: pctY(tier.y - 70) }}
            aria-hidden="true"
          >
            {tier.label}
          </span>
        ))}

        {activeId &&
          MAP_EDGES.filter((edge) => edgeTouches(edge, activeId)).map(
            (edge) => {
              const from = findNode(edge.from);
              const to = findNode(edge.to);
              if (!from || !to) return null;
              const [x, y] = edgeGeometry(from, to).mid;
              return (
                <span
                  key={`label-${edge.from}-${edge.to}`}
                  className="map-edge-label pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 whitespace-nowrap bg-paper px-1 font-mono text-xs text-accent"
                  style={{ left: pctX(x), top: pctY(y) }}
                  aria-hidden="true"
                >
                  {edge.label}
                </span>
              );
            }
          )}

        {MAP_NODES.map((node) => {
          const state = nodeState(node.id);
          const figure = node.figureId ? figures.get(node.figureId) : undefined;
          const common = {
            ref: (el: HTMLElement | null) => {
              if (el) nodeRefs.current.set(node.id, el);
              else nodeRefs.current.delete(node.id);
            },
            'aria-label': nodeDescription(node),
            tabIndex: node.id === focusId ? 0 : -1,
            'data-state': state,
            'data-node': node.id,
            className:
              'map-node absolute flex flex-col justify-center gap-0.5 border bg-paper-raised px-3 text-left',
            style: {
              left: pctX(node.x - NODE_HALF.width),
              top: pctY(node.y - NODE_HALF.height),
              width: pctX(NODE_HALF.width * 2),
              height: pctY(NODE_HALF.height * 2),
            },
            onMouseEnter: () => setActiveId(node.id),
            onFocus: () => {
              setActiveId(node.id);
              setFocusId(node.id);
            },
            onBlur: () => setActiveId(null),
            onKeyDown: (event: React.KeyboardEvent) =>
              onNodeKeyDown(event, node),
          };
          const body = <NodeBody node={node} figure={figure} />;
          const href = node.href;
          return href ? (
            <Link
              key={node.id}
              to={href}
              {...common}
              onClick={(event) => openCaseStudy(event, href)}
            >
              {body}
            </Link>
          ) : (
            <div key={node.id} role="group" {...common}>
              {body}
            </div>
          );
        })}
      </div>

      <ol className="space-y-8 lg:hidden" aria-label="System map as a list">
        {MAP_TIERS.map((tier) => (
          <li key={tier.id}>
            <p className="mono-label border-b border-line pb-2">{tier.label}</p>
            <ul className="border-l border-line">
              {MAP_NODES.filter((node) => node.tier === tier.id).map((node) => {
                const figure = node.figureId
                  ? figures.get(node.figureId)
                  : undefined;
                const links = MAP_EDGES.filter(
                  (edge) => edge.from === node.id
                ).map((edge) => {
                  const other = findNode(edge.to);
                  return other ? `${edge.label} ${other.label}` : '';
                });
                const content = (
                  <>
                    <NodeBody node={node} figure={figure} />
                    {links.length > 0 && (
                      <span className="mt-1 block font-mono text-xs text-ink-faint">
                        {links.join(', ')}
                      </span>
                    )}
                  </>
                );
                const ref = (el: HTMLElement | null) => {
                  if (el) itemRefs.current.set(node.id, el);
                  else itemRefs.current.delete(node.id);
                };
                return (
                  <li key={node.id} className="border-b border-line">
                    {node.href ? (
                      <Link
                        ref={ref}
                        to={node.href}
                        className="block py-3 pl-4 pr-1 transition-colors hover:bg-paper-sunk"
                      >
                        {content}
                      </Link>
                    ) : (
                      <div ref={ref} tabIndex={-1} className="py-3 pl-4 pr-1">
                        {content}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
};

export default SystemMap;
