import { describe, expect, it } from 'vitest';
import {
  listCaseStudies,
  listWork,
  manName,
  mapNodeForCaseStudy,
  resolveCaseStudy,
} from './caseStudies';
import type { CaseStudy, Project } from './types';

const study = (
  slug: string,
  data: Record<string, string>,
  body = ''
): CaseStudy => ({ slug, data, body });

const project = (overrides: Partial<Project>): Project => ({
  id: 1,
  title: 'Project',
  description: 'A project description.',
  image: '',
  technologies: ['Python'],
  featured: false,
  display_order: 0,
  created_at: '2026-01-01',
  ...overrides,
});

describe('resolveCaseStudy', () => {
  it('returns undefined with neither source', () => {
    expect(resolveCaseStudy('none', undefined, undefined)).toBeUndefined();
  });

  it('renders from frontmatter alone', () => {
    const view = resolveCaseStudy(
      'aws-organisation',
      study(
        'aws-organisation',
        {
          title: 'AWS organisation',
          summary: 'Accounts.',
          role: 'Owner',
          stack: 'Terraform, AWS ',
          period: '2026',
          map_node: 'aws-org',
        },
        '## Problem\n\nText.'
      ),
      undefined
    );
    expect(view).toMatchObject({
      title: 'AWS organisation',
      summary: 'Accounts.',
      role: 'Owner',
      period: '2026',
      stack: ['Terraform', 'AWS'],
      hasWriteUp: true,
      links: [],
      mapNodeId: 'aws-org',
    });
  });

  it('falls back to the project for missing fields', () => {
    const view = resolveCaseStudy(
      'webbpulse-portfolio',
      undefined,
      project({
        title: 'Portfolio',
        live_url: 'https://example.com',
        github_url: 'https://github.com/example',
      })
    );
    expect(view?.title).toBe('Portfolio');
    expect(view?.summary).toBe('A project description.');
    expect(view?.body).toBe('A project description.');
    expect(view?.hasWriteUp).toBe(false);
    expect(view?.stack).toEqual(['Python']);
    expect(view?.links.map((link) => link.label)).toEqual([
      'Live site',
      'Source on GitHub',
    ]);
    expect(view?.mapNodeId).toBe('portfolio');
  });

  it('prefers frontmatter over the project', () => {
    const view = resolveCaseStudy(
      'standupless',
      study('standupless', { title: 'From file' }, 'Body'),
      project({ title: 'From project' })
    );
    expect(view?.title).toBe('From file');
  });
});

describe('mapNodeForCaseStudy', () => {
  it('uses a named node only when it exists', () => {
    expect(mapNodeForCaseStudy('standupless', 'carmodpicker')).toBe(
      'carmodpicker'
    );
    expect(mapNodeForCaseStudy('standupless', 'nope')).toBe('standupless');
    expect(mapNodeForCaseStudy('unknown')).toBeUndefined();
  });
});

describe('listCaseStudies and listWork', () => {
  const studies = [
    study('zeta', { title: 'Zeta' }, 'Body'),
    study('aws-organisation', { title: 'AWS' }, 'Body'),
    study('standupless', { title: 'Standupless' }, 'Body'),
  ];

  it('orders case studies by the map, then by slug', () => {
    expect(listCaseStudies(studies).map((entry) => entry.slug)).toEqual([
      'standupless',
      'aws-organisation',
      'zeta',
    ]);
  });

  it('adds projects without a case study after the case studies', () => {
    const work = listWork(studies, [
      project({ slug: 'standupless', title: 'Ignored' }),
      project({ slug: 'crawler', title: 'Crawler' }),
      project({ title: 'No slug' }),
    ]);
    expect(work.map((entry) => entry.slug)).toEqual([
      'standupless',
      'aws-organisation',
      'zeta',
      'crawler',
    ]);
    expect(work[0]?.title).toBe('Standupless');
    expect(work[3]?.hasWriteUp).toBe(false);
  });
});

describe('manName', () => {
  it('upper-cases the slug', () => {
    expect(manName('webbpulse-terraform')).toBe('WEBBPULSE-TERRAFORM');
  });
});
