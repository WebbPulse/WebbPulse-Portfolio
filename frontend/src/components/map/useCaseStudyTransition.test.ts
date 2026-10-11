import { afterEach, describe, expect, it, vi } from 'vitest';
import { waitForElement } from './useCaseStudyTransition';

describe('waitForElement', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('resolves at once when the element is already there', async () => {
    document.body.innerHTML = '<header data-case-study-head></header>';
    await expect(
      waitForElement('[data-case-study-head]', 1000)
    ).resolves.toBeUndefined();
  });

  it('resolves when the element is added, without animation frames', async () => {
    const raf = vi.spyOn(window, 'requestAnimationFrame');
    const waiting = waitForElement('[data-case-study-head]', 5000);
    const header = document.createElement('header');
    header.setAttribute('data-case-study-head', '');
    document.body.appendChild(header);
    await expect(waiting).resolves.toBeUndefined();
    expect(raf).not.toHaveBeenCalled();
  });

  it('resolves after the timeout when the element never appears', async () => {
    vi.useFakeTimers();
    try {
      const waiting = waitForElement('[data-case-study-head]', 200);
      vi.advanceTimersByTime(200);
      await expect(waiting).resolves.toBeUndefined();
    } finally {
      vi.useRealTimers();
    }
  });
});
