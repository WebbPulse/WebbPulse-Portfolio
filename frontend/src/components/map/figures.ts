import type { PublicFigure } from '../../services/api';

/** The time of day a figure was read, or nothing when it does not parse. */
export const asOfTime = (iso: string): string => {
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return '';
  return new Date(time).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
    hour12: false,
  });
};

/** The value a figure shows, with site statuses spelled out. */
export const figureValue = (figure: PublicFigure): string =>
  figure.id.startsWith('status-')
    ? figure.value === 'up'
      ? 'Up'
      : 'Down'
    : figure.value;
