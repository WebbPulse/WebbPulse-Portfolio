/// <reference types="@testing-library/jest-dom" />
import { expect, afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import * as matchers from '@testing-library/jest-dom/matchers';

// Extend Vitest's expect method with methods from react-testing-library.
//
// The triple slash reference above is the type half of the same statement.
// `expect.extend` adds the matchers at runtime but tells the compiler nothing,
// so without it `toBeInTheDocument` is a type error in every component test
// even though it works when the suite runs.
expect.extend(matchers);

declare module 'vitest' {
  // The parameter list has to match vitest's own declaration of `Matchers`
  // exactly, or TypeScript refuses the merge.
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type, @typescript-eslint/no-explicit-any
  interface Matchers<T = any>
    extends matchers.TestingLibraryMatchers<unknown, T> {}
}

// Cleanup after each test case (e.g. clearing jsdom)
afterEach(() => {
  cleanup();
});
