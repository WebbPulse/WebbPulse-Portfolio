import { describe, expect, it } from 'vitest';
import {
  MAP_EDGES,
  MAP_NODES,
  connectedTo,
  edgeGeometry,
  findNode,
  nearestInDirection,
  nodeCaseStudySlug,
  nodeDescription,
  type MapNode,
} from './map';

describe('map data', () => {
  it('has unique node ids and edges between real nodes', () => {
    const ids = MAP_NODES.map((node) => node.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const edge of MAP_EDGES) {
      expect(findNode(edge.from)).toBeDefined();
      expect(findNode(edge.to)).toBeDefined();
    }
  });

  it('links the shared nodes to their case studies', () => {
    const slug = (id: string) => {
      const node = findNode(id);
      return node ? nodeCaseStudySlug(node) : undefined;
    };
    expect(slug('standupless')).toBe('standupless');
    expect(slug('control-plane')).toBe('webbpulse-terraform');
    expect(slug('platform-modules')).toBe('platform-packages');
    expect(slug('aws-org')).toBe('aws-organisation');
  });
});

describe('connectedTo', () => {
  it('lists neighbours in both directions without repeats', () => {
    const edges = [
      { from: 'a', to: 'b', label: 'x' },
      { from: 'c', to: 'a', label: 'y' },
      { from: 'a', to: 'b', label: 'z' },
    ];
    expect(connectedTo('a', edges).sort()).toEqual(['b', 'c']);
    expect(connectedTo('d', edges)).toEqual([]);
  });
});

describe('nearestInDirection', () => {
  const at = (id: string, x: number, y: number): MapNode => ({
    id,
    label: id,
    kind: 'k',
    tier: 'products',
    x,
    y,
    facts: [],
  });
  const nodes = [
    at('o', 0, 0),
    at('r', 100, 0),
    at('d', 30, 100),
    at('dr', 60, 60),
  ];

  it('prefers the node straight ahead', () => {
    expect(nearestInDirection('o', 'right', nodes)?.id).toBe('r');
    expect(nearestInDirection('o', 'down', nodes)?.id).toBe('d');
  });

  it('returns undefined at the edge of the map', () => {
    expect(nearestInDirection('o', 'left', nodes)).toBeUndefined();
    expect(nearestInDirection('o', 'up', nodes)).toBeUndefined();
    expect(nearestInDirection('missing', 'up', nodes)).toBeUndefined();
  });
});

describe('edgeGeometry', () => {
  it('draws a straight run between nodes in one tier', () => {
    const from = findNode('control-plane');
    const to = findNode('platform-modules');
    const a = findNode('standupless');
    const b = findNode('carmodpicker');
    if (!from || !to || !a || !b) throw new Error('missing node');
    expect(edgeGeometry(a, b).path).toBe('M 250 90 L 270 90');
    expect(edgeGeometry(from, to).path).toContain(' C ');
  });
});

describe('nodeDescription', () => {
  it('names the node, its facts and its connections', () => {
    const node = findNode('aws-org');
    if (!node) throw new Error('missing node');
    const text = nodeDescription(node);
    expect(text.startsWith(`${node.label}, ${node.kind}.`)).toBe(true);
    expect(text).toContain('Connections:');
  });
});
