/** The drawing space the map's coordinates are measured in. */
export const MAP_VIEWBOX = { width: 1000, height: 600 } as const;

/** The three bands of the map, from top to bottom. */
export type MapTier = 'products' | 'shared' | 'aws';

/** One box on the system map. */
export interface MapNode {
  id: string;
  label: string;
  kind: string;
  tier: MapTier;
  x: number;
  y: number;
  facts: string[];
  href?: string;
  figureId?: string;
}

/** One labelled connection between two nodes. */
export interface MapEdge {
  from: string;
  to: string;
  label: string;
}

/** The label and vertical centre of each band. */
export const MAP_TIERS: { id: MapTier; label: string; y: number }[] = [
  { id: 'products', label: 'Products', y: 90 },
  { id: 'shared', label: 'Shared packages', y: 300 },
  { id: 'aws', label: 'AWS organisation', y: 510 },
];

/** Every node on the map, in reading order. */
export const MAP_NODES: MapNode[] = [
  {
    id: 'standupless',
    label: 'Standupless',
    kind: 'Issue tracker',
    tier: 'products',
    x: 140,
    y: 90,
    facts: ['294 routes', '22 tables', '151 MCP tools'],
    href: '/work/standupless',
    figureId: 'status-standupless',
  },
  {
    id: 'carmodpicker',
    label: 'CarModPicker',
    kind: 'Build tracker',
    tier: 'products',
    x: 380,
    y: 90,
    facts: ['150 routes', '27 tables', 'MV3 extension'],
    href: '/work/carmodpicker',
    figureId: 'status-carmodpicker',
  },
  {
    id: 'portfolio',
    label: 'Portfolio',
    kind: 'This site',
    tier: 'products',
    x: 620,
    y: 90,
    facts: ['React on CloudFront', 'FastAPI on Lambda'],
    href: '/work/webbpulse-portfolio',
    figureId: 'status-portfolio',
  },
  {
    id: 'control-plane',
    label: 'Terraform plane',
    kind: 'Control plane',
    tier: 'products',
    x: 860,
    y: 90,
    facts: ['11 workspaces', '25 Fargate runners'],
    href: '/work/webbpulse-terraform',
  },
  {
    id: 'webbpulse-python',
    label: 'webbpulse',
    kind: 'Python package',
    tier: 'shared',
    x: 220,
    y: 300,
    facts: ['18 modules', '6 subpackages'],
    href: '/work/platform-packages',
    figureId: 'release-webbpulse-python',
  },
  {
    id: 'webbpulse-typescript',
    label: '@webbpulse/*',
    kind: 'TypeScript packages',
    tier: 'shared',
    x: 500,
    y: 300,
    facts: ['7 packages', 'ESM only'],
    href: '/work/platform-packages',
    figureId: 'release-webbpulse-typescript',
  },
  {
    id: 'platform-modules',
    label: 'platform-modules',
    kind: 'Terraform modules',
    tier: 'shared',
    x: 780,
    y: 300,
    facts: ['23 modules', '36 examples'],
    href: '/work/platform-packages',
    figureId: 'release-terraform-aws-platform-modules',
  },
  {
    id: 'artifacts',
    label: 'Artifacts',
    kind: 'CodeArtifact and ECR',
    tier: 'aws',
    x: 300,
    y: 510,
    facts: ['5 repositories', '1 base image'],
    href: '/work/aws-organisation',
  },
  {
    id: 'aws-org',
    label: 'AWS organisation',
    kind: 'Accounts and guardrails',
    tier: 'aws',
    x: 700,
    y: 510,
    facts: ['9 accounts', '6 OUs', 'Cost kill switch'],
    href: '/work/aws-organisation',
  },
];

/** Every connection on the map. */
export const MAP_EDGES: MapEdge[] = [
  { from: 'standupless', to: 'webbpulse-python', label: 'imports' },
  { from: 'standupless', to: 'webbpulse-typescript', label: 'imports' },
  { from: 'carmodpicker', to: 'webbpulse-python', label: 'imports' },
  { from: 'carmodpicker', to: 'webbpulse-typescript', label: 'imports' },
  { from: 'portfolio', to: 'webbpulse-python', label: 'imports' },
  { from: 'portfolio', to: 'webbpulse-typescript', label: 'imports' },
  { from: 'control-plane', to: 'webbpulse-python', label: 'imports' },
  { from: 'control-plane', to: 'platform-modules', label: 'serves registry' },
  { from: 'webbpulse-python', to: 'artifacts', label: 'publishes to' },
  { from: 'webbpulse-typescript', to: 'artifacts', label: 'publishes to' },
  { from: 'platform-modules', to: 'aws-org', label: 'provisions' },
  { from: 'control-plane', to: 'aws-org', label: 'applies to' },
  { from: 'artifacts', to: 'aws-org', label: 'runs in' },
];

/** The node with `id`, if there is one. */
export function findNode(id: string): MapNode | undefined {
  return MAP_NODES.find((node) => node.id === id);
}

/** The ids of every node one edge away from `id`. */
export function connectedTo(
  id: string,
  edges: MapEdge[] = MAP_EDGES
): string[] {
  const ids = new Set<string>();
  for (const edge of edges) {
    if (edge.from === id) ids.add(edge.to);
    if (edge.to === id) ids.add(edge.from);
  }
  return [...ids];
}

/** True when the edge touches the node `id`. */
export function edgeTouches(edge: MapEdge, id: string | null): boolean {
  return id !== null && (edge.from === id || edge.to === id);
}

/** The arrow keys the map moves focus with. */
export type MapDirection = 'up' | 'down' | 'left' | 'right';

/**
 * The nearest node from `fromId` in `direction`, or undefined at an edge.
 *
 * Distance along the direction counts fully and sideways drift counts double,
 * so a node straight ahead wins over a closer one off to the side.
 */
export function nearestInDirection(
  fromId: string,
  direction: MapDirection,
  nodes: MapNode[] = MAP_NODES
): MapNode | undefined {
  const from = nodes.find((node) => node.id === fromId);
  if (!from) return undefined;
  let best: MapNode | undefined;
  let bestScore = Infinity;
  for (const node of nodes) {
    if (node.id === from.id) continue;
    const dx = node.x - from.x;
    const dy = node.y - from.y;
    const along =
      direction === 'right'
        ? dx
        : direction === 'left'
          ? -dx
          : direction === 'down'
            ? dy
            : -dy;
    const across = direction === 'left' || direction === 'right' ? dy : dx;
    if (along <= 0) continue;
    const score = along + Math.abs(across) * 2;
    if (score < bestScore) {
      bestScore = score;
      best = node;
    }
  }
  return best;
}

/** Half the width and height of a node box, in map units. */
export const NODE_HALF = { width: 105, height: 34 } as const;

/** Where an edge is drawn: its path, both endpoints and its midpoint. */
export interface EdgeGeometry {
  path: string;
  start: [number, number];
  end: [number, number];
  mid: [number, number];
}

/**
 * The drawing for an edge: a vertical S-curve between tiers, or a straight run
 * between the facing sides of two nodes in the same tier.
 */
export function edgeGeometry(from: MapNode, to: MapNode): EdgeGeometry {
  if (from.y === to.y) {
    const right = to.x > from.x;
    const x1 = from.x + (right ? NODE_HALF.width : -NODE_HALF.width);
    const x2 = to.x + (right ? -NODE_HALF.width : NODE_HALF.width);
    return {
      path: `M ${x1} ${from.y} L ${x2} ${to.y}`,
      start: [x1, from.y],
      end: [x2, to.y],
      mid: [(x1 + x2) / 2, from.y],
    };
  }
  const down = to.y > from.y;
  const y1 = from.y + (down ? NODE_HALF.height : -NODE_HALF.height);
  const y2 = to.y + (down ? -NODE_HALF.height : NODE_HALF.height);
  const mid = (y1 + y2) / 2;
  return {
    path: `M ${from.x} ${y1} C ${from.x} ${mid} ${to.x} ${mid} ${to.x} ${y2}`,
    start: [from.x, y1],
    end: [to.x, y2],
    mid: [(from.x + to.x) / 2, mid],
  };
}

/** The sentence a screen reader hears for a node, connections included. */
export function nodeDescription(
  node: MapNode,
  edges: MapEdge[] = MAP_EDGES
): string {
  const links = edges
    .filter((edge) => edgeTouches(edge, node.id))
    .map((edge) => {
      const other = findNode(edge.from === node.id ? edge.to : edge.from);
      if (!other) return '';
      return edge.from === node.id
        ? `${edge.label} ${other.label}`
        : `${other.label} ${edge.label} it`;
    })
    .filter(Boolean);
  const parts = [`${node.label}, ${node.kind}`, node.facts.join(', ')];
  if (links.length) parts.push(`Connections: ${links.join('; ')}`);
  return `${parts.join('. ')}.`;
}

/** The case study slug a node links to, if it links to one. */
export function nodeCaseStudySlug(node: MapNode): string | undefined {
  return node.href?.startsWith('/work/')
    ? node.href.slice('/work/'.length)
    : undefined;
}
