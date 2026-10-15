import { describe, expect, it } from 'vitest';
import {
  getCertifications,
  getEducation,
  getExperience,
  getProjects,
  getSiteContent,
  getSkills,
} from '.';

describe('committed content', () => {
  it('carries every public section', () => {
    expect(getSiteContent().hero_subtitle).toBeTruthy();
    expect(getProjects().length).toBeGreaterThan(0);
    expect(getExperience().length).toBeGreaterThan(0);
    expect(getSkills().length).toBeGreaterThan(0);
    expect(getEducation().length).toBeGreaterThan(0);
    expect(getCertifications().length).toBeGreaterThan(0);
  });

  it('gives every project a unique slug and a local image', () => {
    const slugs = getProjects().map((p) => p.slug);

    expect(slugs.every(Boolean)).toBe(true);
    expect(new Set(slugs).size).toBe(slugs.length);
    for (const project of getProjects()) {
      expect(project.image.startsWith('/projects/')).toBe(true);
    }
  });

  it('keeps ids unique within each list', () => {
    for (const list of [
      getProjects(),
      getExperience(),
      getSkills(),
      getEducation(),
      getCertifications(),
    ]) {
      const ids = list.map((item) => item.id);
      expect(new Set(ids).size).toBe(ids.length);
    }
  });
});
