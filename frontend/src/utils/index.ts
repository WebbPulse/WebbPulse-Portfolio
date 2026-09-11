export * from './validation';
export * from './formatting';
export * from './socialIcons';
export * from './socialPlatforms';
export * from './markdown';

/**
 * Generates a placeholder image URL or returns null for CSS-based placeholder
 * @returns null to indicate CSS placeholder should be used
 */
export const getPlaceholderImage = (): string | null => {
  return null;
};
