import { lazy, type ComponentType, type FC } from 'react';

/** A page component split into its own chunk that can be loaded ahead of use. */
export type LazyPage = FC & {
  preload: () => Promise<void>;
};

/**
 * Wraps a page in its own chunk.
 *
 * Once `preload` has resolved the page renders synchronously, so a prerendered
 * route hydrates without suspending. Before that it suspends like
 * `React.lazy`.
 */
export function lazyPage(load: () => Promise<ComponentType>): LazyPage {
  let loaded: ComponentType | undefined;
  let pending: Promise<void> | undefined;
  const preload = (): Promise<void> => {
    pending ??= load().then(
      (component) => {
        loaded = component;
      },
      (error: unknown) => {
        pending = undefined;
        throw error;
      }
    );
    return pending;
  };
  const Deferred = lazy(async () => {
    await preload();
    return { default: loaded as ComponentType };
  });
  const Page: FC = () => {
    const Component = loaded ?? Deferred;
    return <Component />;
  };
  return Object.assign(Page, { preload });
}
