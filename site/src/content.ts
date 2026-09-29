/** A product WebbPulse builds and runs, as shown on the landing page. */
export interface Product {
  name: string;
  url: string;
  host: string;
  summary: string;
  body: string;
  facts: { label: string; value: string }[];
}

/** A contact route, rendered as a link in the contact section. */
export interface ContactLink {
  label: string;
  href: string;
  display: string;
}

export const SITE_URL = 'https://webbpulse.com/';

export const PORTFOLIO_URL = 'https://portfolio.webbpulse.com';

export const PRODUCTS: Product[] = [
  {
    name: 'Standupless',
    url: 'https://standupless.dev',
    host: 'standupless.dev',
    summary: 'An issue tracker for small software teams.',
    body: 'Teams, cycles, projects and a roadmap, with list and board views you can filter and save. A GitHub App links pull requests to issues and moves them as the work ships. An API, webhooks, a CLI and an MCP server let scripts and coding agents work in it too.',
    facts: [
      { label: 'For', value: 'Software teams' },
      { label: 'Status', value: 'Live' },
      { label: 'Note', value: 'WebbPulse plans its own work in it' },
    ],
  },
  {
    name: 'CarModPicker',
    url: 'https://www.carmodpicker.com',
    host: 'carmodpicker.com',
    summary: 'Plan, track and share a car build.',
    body: 'Keep your cars and build lists, attach parts to phased builds and log progress in forum-style threads. A Chrome extension captures part details straight from retailer pages. Free to use, with a Premium plan that removes ads and lifts the build list limit.',
    facts: [
      { label: 'For', value: 'Car enthusiasts' },
      { label: 'Status', value: 'Live' },
      { label: 'Extras', value: 'Chrome extension' },
    ],
  },
];

export const PRACTICES: { title: string; body: string }[] = [
  {
    title: 'Serverless on AWS',
    body: 'The products run on Lambda, DynamoDB and CloudFront, with staging and production in separate AWS accounts.',
  },
  {
    title: 'Infrastructure as code',
    body: 'Every environment is defined in Terraform, and every change is planned and reviewed before it is applied.',
  },
  {
    title: 'Shared foundations',
    body: 'Sign-in, configuration and deployment live in shared Python and TypeScript packages, so a fix reaches every product.',
  },
  {
    title: 'Staging first',
    body: 'Changes pass CI and end to end tests on a staging environment before they are promoted to production.',
  },
];

export const CONTACT_EMAIL = 'hello@webbpulse.com';

export const CONTACT_LINKS: ContactLink[] = [
  {
    label: 'Email',
    href: `mailto:${CONTACT_EMAIL}`,
    display: CONTACT_EMAIL,
  },
  {
    label: 'GitHub',
    href: 'https://github.com/WebbPulse',
    display: 'github.com/WebbPulse',
  },
];
