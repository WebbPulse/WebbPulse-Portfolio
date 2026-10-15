import type { NavigationItem } from '../../types';

/** The site sections, as in-page anchors for use on the home page. */
export const HOME_NAV: NavigationItem[] = [
  { label: 'Work', href: '#work' },
  { label: 'Experience', href: '#experience' },
  { label: 'Skills', href: '#skills' },
  { label: 'Writing', href: '#writing' },
  { label: 'Contact', href: '#contact' },
];

/** The same sections linked from any other page of the site. */
export const SITE_NAV: NavigationItem[] = [
  { label: 'Work', href: '/#work' },
  { label: 'Experience', href: '/#experience' },
  { label: 'Skills', href: '/#skills' },
  { label: 'Writing', href: '/blog' },
  { label: 'Contact', href: '/#contact' },
];
