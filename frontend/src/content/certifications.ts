import type { Certification } from './types';

/** The certifications. */
export const certifications: Certification[] = [
  {
    id: 1,
    name: 'AWS Certified Cloud Practitioner',
    issuer: 'Amazon Web Services',
    issued_date: '2023-01-01',
    order: 10,
    created_at: '2026-05-10T02:22:31.563043Z',
  },
  {
    id: 2,
    name: 'CCNA: Switching, Routing, and Wireless Essentials',
    issuer: 'Cisco',
    issued_date: '2022-01-01',
    order: 20,
    created_at: '2026-05-10T02:22:31.563043Z',
  },
  {
    id: 3,
    name: 'CCNA: Enterprise Networking, Security, and Automation',
    issuer: 'Cisco',
    issued_date: '2022-01-01',
    order: 30,
    created_at: '2026-05-10T02:22:31.563043Z',
  },
  {
    id: 4,
    name: 'Microsoft Certified: Azure Fundamentals',
    issuer: 'Microsoft',
    issued_date: '2022-01-01',
    order: 40,
    created_at: '2026-05-10T02:22:31.563043Z',
  },
];
