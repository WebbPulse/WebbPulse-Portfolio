// Portfolio's lint rules come from @webbpulse/eslint-config. The shared react
// config supplies the type checked TypeScript rules with the no-unsafe-* family
// and no-explicit-any promoted to errors, plus eslint-config-prettier last.
//
// The React plugins are passed in rather than depended on by the shared config,
// because the two applications are on different plugin sets. Portfolio runs
// react-hooks and react-refresh.
import { reactConfig } from '@webbpulse/eslint-config/react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import prettier from 'eslint-plugin-prettier';

export default [
  ...reactConfig({
    project: ['./tsconfig.app.json', './tsconfig.node.json'],
    tsconfigRootDir: import.meta.dirname,
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
  }),
  {
    // Portfolio specific: formatting is enforced as a lint error as well as by
    // the separate format:check script, which is how this repository has always
    // run it. The shared config only turns conflicting rules off.
    files: ['**/*.{ts,tsx}'],
    plugins: { prettier },
    rules: {
      'prettier/prettier': 'error',
    },
  },
];
