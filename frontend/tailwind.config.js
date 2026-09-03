/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Deep navy/black surface palette - dark mode is default
        surface: {
          50: '#f8fafc',
          100: '#e2e8f0',
          200: '#cbd5e1',
          300: '#94a3b8',
          400: '#64748b',
          500: '#475569',
          600: '#334155',
          700: '#1e293b',
          800: '#0f172a',
          850: '#0a1020',
          900: '#070b18',
          950: '#03060f',
        },
        // Cyan accent
        accent: {
          cyan: {
            300: '#67e8f9',
            400: '#22d3ee',
            500: '#06b6d4',
            600: '#0891b2',
          },
          violet: {
            300: '#c4b5fd',
            400: '#a78bfa',
            500: '#8b5cf6',
            600: '#7c3aed',
          },
          fuchsia: {
            300: '#f0abfc',
            400: '#e879f9',
            500: '#d946ef',
            600: '#c026d3',
          },
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        display: [
          '"Space Grotesk"',
          'Inter',
          'ui-sans-serif',
          'system-ui',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          'Liberation Mono',
          'Courier New',
          'monospace',
        ],
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic':
          'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
        'mesh-1':
          'radial-gradient(at 20% 20%, rgba(6, 182, 212, 0.18) 0px, transparent 50%), radial-gradient(at 80% 0%, rgba(139, 92, 246, 0.18) 0px, transparent 50%), radial-gradient(at 80% 80%, rgba(217, 70, 239, 0.15) 0px, transparent 50%), radial-gradient(at 0% 100%, rgba(6, 182, 212, 0.10) 0px, transparent 50%)',
        'gradient-accent':
          'linear-gradient(135deg, #06b6d4 0%, #8b5cf6 50%, #d946ef 100%)',
      },
      boxShadow: {
        'glow-cyan':
          '0 0 24px -4px rgba(6, 182, 212, 0.4), 0 0 64px -16px rgba(6, 182, 212, 0.25)',
        'glow-violet':
          '0 0 24px -4px rgba(139, 92, 246, 0.4), 0 0 64px -16px rgba(139, 92, 246, 0.25)',
        'glow-fuchsia':
          '0 0 24px -4px rgba(217, 70, 239, 0.4), 0 0 64px -16px rgba(217, 70, 239, 0.25)',
        'glow-soft':
          '0 0 16px -2px rgba(139, 92, 246, 0.25), 0 0 48px -12px rgba(6, 182, 212, 0.15)',
      },
      keyframes: {
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(24px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'gradient-shift': {
          '0%, 100%': { 'background-position': '0% 50%' },
          '50%': { 'background-position': '100% 50%' },
        },
        'glow-pulse': {
          '0%, 100%': { 'box-shadow': '0 0 0 0 rgba(139, 92, 246, 0.4)' },
          '50%': { 'box-shadow': '0 0 0 14px rgba(139, 92, 246, 0)' },
        },
        'blob-float-1': {
          '0%, 100%': { transform: 'translate(0px, 0px) scale(1)' },
          '33%': { transform: 'translate(30px, -50px) scale(1.1)' },
          '66%': { transform: 'translate(-20px, 30px) scale(0.95)' },
        },
        'blob-float-2': {
          '0%, 100%': { transform: 'translate(0px, 0px) scale(1)' },
          '33%': { transform: 'translate(-40px, 30px) scale(1.05)' },
          '66%': { transform: 'translate(20px, -40px) scale(1.1)' },
        },
        'blob-float-3': {
          '0%, 100%': { transform: 'translate(0px, 0px) scale(1)' },
          '50%': { transform: 'translate(40px, 40px) scale(1.08)' },
        },
        'slow-spin': {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
      },
      animation: {
        'fade-in-up': 'fade-in-up 0.7s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'fade-in': 'fade-in 0.6s ease-out forwards',
        'gradient-shift': 'gradient-shift 8s ease infinite',
        'glow-pulse': 'glow-pulse 2.4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'blob-1': 'blob-float-1 18s ease-in-out infinite',
        'blob-2': 'blob-float-2 22s ease-in-out infinite',
        'blob-3': 'blob-float-3 26s ease-in-out infinite',
        'slow-spin': 'slow-spin 12s linear infinite',
      },
      typography: {
        DEFAULT: {
          css: {
            maxWidth: 'none',
            color: '#cbd5e1',
            a: {
              color: '#22d3ee',
              '&:hover': { color: '#67e8f9' },
            },
            'h1, h2, h3, h4, h5, h6': {
              color: '#f8fafc',
              fontFamily: '"Space Grotesk", Inter, sans-serif',
              fontWeight: '700',
              lineHeight: '1.2',
            },
            h1: {
              fontSize: '2.25rem',
              marginTop: '1rem',
              marginBottom: '0.5rem',
            },
            h2: {
              fontSize: '1.875rem',
              marginTop: '0.75rem',
              marginBottom: '0.375rem',
            },
            h3: {
              fontSize: '1.5rem',
              marginTop: '0.75rem',
              marginBottom: '0.375rem',
            },
            'p, ul, ol': { marginTop: '0.5rem', marginBottom: '0.5rem' },
            'ul, ol': { paddingLeft: '1.625rem' },
            li: { marginTop: '0.125rem', marginBottom: '0.125rem' },
            'li > p': { marginTop: '0.25rem', marginBottom: '0.25rem' },
            'li > ul, li > ol': {
              marginTop: '0.25rem',
              marginBottom: '0.25rem',
            },
            blockquote: {
              borderLeftColor: '#22d3ee',
              borderLeftWidth: '4px',
              paddingLeft: '1rem',
              fontStyle: 'italic',
              color: '#94a3b8',
              backgroundColor: 'rgba(15, 23, 42, 0.6)',
              borderRadius: '0.375rem',
              padding: '1rem',
              margin: '0.75rem 0',
            },
            code: {
              color: '#e0e7ff',
              backgroundColor: 'rgba(15, 23, 42, 0.7)',
              padding: '0.125rem 0.375rem',
              borderRadius: '0.375rem',
              fontSize: '0.875em',
              fontWeight: '500',
              border: '1px solid rgba(99, 102, 241, 0.15)',
            },
            'pre code': {
              backgroundColor: 'transparent',
              padding: '0',
              color: '#e5e7eb',
              border: 'none',
            },
            pre: {
              backgroundColor: '#0a1020',
              color: '#e5e7eb',
              padding: '1rem',
              borderRadius: '0.5rem',
              overflow: 'auto',
              fontSize: '0.875rem',
              lineHeight: '1.5',
              border: '1px solid rgba(99, 102, 241, 0.12)',
            },
            img: { borderRadius: '0.5rem', margin: '1rem auto' },
            'thead th': {
              backgroundColor: 'rgba(15, 23, 42, 0.6)',
              borderBottom: '1px solid rgba(148, 163, 184, 0.2)',
              padding: '0.75rem',
              fontWeight: '600',
            },
            'tbody td': {
              borderBottom: '1px solid rgba(148, 163, 184, 0.1)',
              padding: '0.75rem',
            },
            hr: { borderColor: 'rgba(148, 163, 184, 0.15)', margin: '1rem 0' },
          },
        },
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
};
