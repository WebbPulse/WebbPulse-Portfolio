# Source Directory Structure

This directory contains the main application code organized into logical modules.

## Directory Structure

```
src/
├── components/          # Reusable UI components
│   ├── common/         # Common components (Button, Card, etc.)
│   ├── layout/         # Layout components (Header, Footer, etc.)
│   └── sections/       # Page sections (Hero, About, etc.)
├── pages/              # Page components
├── hooks/              # Custom React hooks
├── utils/              # Utility functions
├── types/              # TypeScript type definitions
├── assets/             # Static assets
└── styles/             # Global styles
```

## Components

### Common Components (`components/common/`)

Reusable UI components that can be used throughout the application:

- `Button.tsx` - Reusable button component with multiple variants
- `Card.tsx` - Card component for displaying content

### Layout Components (`components/layout/`)

Components that define the overall page structure:

- `Header.tsx` - Navigation header with mobile menu
- `Footer.tsx` - Page footer with social links

### Section Components (`components/sections/`)

Components that represent major page sections:

- `Hero.tsx` - Hero section for the landing area

## Pages (`pages/`)

Page-level components that compose sections and layout:

- `Home.tsx` - Main home page component

## Hooks (`hooks/`)

Custom React hooks for reusable logic:

- `useScrollPosition.ts` - Hook for tracking scroll position
- `useLocalStorage.ts` - Hook for localStorage management

## Utils (`utils/`)

Utility functions for common operations:

- `validation.ts` - Form validation utilities

## Types (`types/`)

TypeScript type definitions and interfaces:

- `index.ts` - Common interfaces for components and data

## Styles (`styles/`)

Global styles and Tailwind CSS configuration:

- `globals.css` - Global styles with Tailwind directives

## Usage

Import components and utilities using the barrel exports:

```typescript
// Import components
import { Button, Card } from './components/common';
import { Header, Footer } from './components/layout';
import { Hero } from './components/sections';

// Import hooks
import { useScrollPosition, useLocalStorage } from './hooks';

// Import utilities
import { validateEmail } from './utils';

// Import types
import { ButtonProps, Project } from './types';
```

## Development Guidelines

1. **Component Structure**: All components should be functional components with TypeScript interfaces
2. **Styling**: Use Tailwind CSS classes for styling
3. **Responsive Design**: Implement mobile-first responsive design
4. **Accessibility**: Include proper ARIA labels and keyboard navigation
5. **Dark Mode**: Support both light and dark themes
6. **Performance**: Use React.memo() for expensive components when appropriate
