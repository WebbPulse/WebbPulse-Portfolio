import type { Experience } from './types';

/** The work history, one entry per role. */
export const experience: Experience[] = [
  {
    id: 1,
    title: 'Software Engineer',
    company: 'Verkada',
    location: 'San Mateo, CA',
    period: 'April 2026 - Present',
    start_date: '2026-04-01',
    description:
      'Software engineer at Verkada, building privacy-conscious physical security software across cameras, access control, and sensors.',
    technologies: ['Python', 'TypeScript', 'React', 'FastAPI', 'SQL'],
    achievements: [
      'Promoted from Senior Escalation Engineer into a full-time software role.',
      'Ship features and tooling used by the support and escalation orgs I came from.',
    ],
    created_at: '2026-05-10T01:05:31.437482Z',
  },
  {
    id: 2,
    title: 'Senior Escalation Engineer',
    company: 'Verkada',
    location: 'San Mateo, CA',
    period: 'July 2025 - May 2026',
    start_date: '2025-07-01',
    end_date: '2026-05-01',
    description:
      'Led escalation engineering for the most complex customer issues spanning device firmware, networking, and cloud services. Mentored junior engineers and authored runbooks adopted across the team.',
    technologies: ['Python', 'SQL', 'Linux', 'Datadog', 'Networking'],
    achievements: [
      'Owned cross-team root-cause investigations on the highest-severity escalations.',
      'Built internal automation that cut repetitive escalation triage time materially.',
      'Mentored escalation engineers and wrote playbooks adopted org-wide.',
    ],
    created_at: '2026-05-10T01:05:31.638883Z',
  },
  {
    id: 3,
    title: 'Escalation Engineer',
    company: 'Verkada',
    location: 'San Mateo, CA',
    period: 'July 2024 - July 2025',
    start_date: '2024-07-01',
    end_date: '2025-07-01',
    description:
      "Investigated and resolved escalated technical issues across device firmware, networking, and Verkada's cloud platform. Partnered with engineering to drive permanent fixes for recurring problems.",
    technologies: ['Python', 'SQL', 'Linux', 'Wireshark', 'Networking'],
    achievements: [
      'Drove root-cause analysis on tier-3 issues escalated from global support.',
      'Filed reproducible bug reports that closed long-standing platform defects.',
    ],
    created_at: '2026-05-10T01:05:31.807883Z',
  },
  {
    id: 4,
    title: 'Senior Technical Support Engineer',
    company: 'Verkada',
    location: 'San Mateo, CA',
    period: 'February 2024 - July 2024',
    start_date: '2024-02-01',
    end_date: '2024-07-01',
    description:
      'Senior technical support engineer handling complex enterprise escalations and mentoring junior teammates on networking, Linux, and the Verkada platform.',
    technologies: ['Networking', 'Linux', 'SQL', 'Active Directory'],
    achievements: [
      'Resolved complex enterprise escalations across networking and access control.',
      'Onboarded and mentored newer technical support engineers.',
    ],
    created_at: '2026-05-10T01:05:31.992677Z',
  },
  {
    id: 5,
    title: 'Technical Support Engineer',
    company: 'Verkada',
    location: 'San Mateo, CA',
    period: 'July 2022 - February 2024',
    start_date: '2022-07-01',
    end_date: '2024-02-01',
    description:
      'Supported enterprise customers deploying Verkada cameras, access control, and sensors across mixed network environments.',
    technologies: ['Networking', 'Linux', 'Wireshark'],
    achievements: [
      'Diagnosed and resolved customer issues spanning networking, hardware, and cloud config.',
      'Contributed knowledge-base articles still referenced by the support team.',
    ],
    created_at: '2026-05-10T01:05:32.180721Z',
  },
  {
    id: 6,
    title: 'Network Engineer',
    company: 'Midwest Energy, Inc.',
    location: 'Hays, KS',
    period: 'January 2022 - May 2022',
    start_date: '2022-01-01',
    end_date: '2022-05-01',
    description:
      'Network engineer at a regional electric and gas utility. Worked on switching, routing, and wireless infrastructure supporting field operations across western Kansas.',
    technologies: ['Cisco', 'Networking', 'Active Directory'],
    achievements: [
      'Maintained and upgraded Cisco switching and wireless infrastructure.',
      'Supported field operations across a multi-site utility network.',
    ],
    created_at: '2026-05-10T01:05:32.343684Z',
  },
];
