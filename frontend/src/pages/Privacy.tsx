import React from 'react';
import { Header, Footer } from '../components/layout';
import { GradientText } from '../components/common';
import { useSiteContent } from '../hooks';
import type { NavigationItem } from '../types';

const NAV: NavigationItem[] = [
  { label: 'Home', href: '/' },
  { label: 'About', href: '/#about' },
  { label: 'Skills', href: '/#skills' },
  { label: 'Projects', href: '/#projects' },
  { label: 'Experience', href: '/#experience' },
  { label: 'Blog', href: '/blog' },
  { label: 'Contact', href: '/#contact' },
];

/** The date the current wording took effect, shown at the top of the page. */
const EFFECTIVE_DATE = 'September 10, 2026';

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({
  title,
  children,
}) => (
  <section className="space-y-3">
    <h2 className="font-display text-xl font-semibold text-surface-50">
      {title}
    </h2>
    <div className="space-y-3 text-surface-300 leading-relaxed">{children}</div>
  </section>
);

/**
 * The public privacy policy.
 *
 * A plain public route because Google's OAuth consent screen requires a reachable
 * policy URL. Update the wording whenever the data handling changes.
 */
export const Privacy: React.FC = () => {
  const { data } = useSiteContent();
  const email = data?.email ?? 'tyler@webbpulse.com';

  return (
    <div className="min-h-screen">
      <Header navigationItems={NAV} />
      <main className="relative py-20 sm:py-28 overflow-hidden">
        <div className="absolute inset-0 bg-mesh-1 opacity-40 pointer-events-none" />

        <div className="relative z-10 max-w-3xl mx-auto px-6 sm:px-8">
          <header className="mb-12">
            <h1 className="font-display text-4xl sm:text-5xl font-bold text-surface-50 mb-4">
              <GradientText as="span">Privacy Policy</GradientText>
            </h1>
            <p className="text-surface-400 text-sm">
              Effective {EFFECTIVE_DATE}
            </p>
          </header>

          <div className="space-y-10">
            <Section title="About this site">
              <p>
                webbpulse.com is the personal portfolio site of Tyler Webb, a
                software engineer. It publishes writing and project information.
                You can read every public page without signing in and without
                giving me any personal information.
              </p>
            </Section>

            <Section title="What is collected">
              <p>
                <strong className="text-surface-100">Server logs.</strong> The
                API records ordinary request information: the IP address the
                request came from, the time, the method and path, and the
                response status. Browser user agents are not recorded. These
                logs exist to keep the site running and to investigate errors
                and abuse.
              </p>
              <p>
                <strong className="text-surface-100">Sign-in data.</strong> Sign
                in is for the site owner and administrators only. There is no
                public sign up, so if you are reading this as a visitor, none of
                it applies to you. An administrator account holds a username, an
                email address, and whether the account is active and verified.
              </p>
              <p>
                <strong className="text-surface-100">
                  Sign in with GitHub or Google.
                </strong>{' '}
                Administrators can sign in through GitHub or Google instead of a
                password. When someone does, the provider returns the email
                address on their account and the identifier it assigns to it,
                and those are stored so the account can be recognised next time.
                A password is never received from a provider.
              </p>
              <p>
                <strong className="text-surface-100">Failed sign-ins.</strong>{' '}
                To slow down password guessing, the IP address of a failed
                sign-in attempt is recorded for 15 minutes and then deleted
                automatically.
              </p>
              <p>
                <strong className="text-surface-100">
                  Cookies and browser storage.
                </strong>{' '}
                Nothing is stored in your browser until you sign in. Signing in
                keeps a session going, using a cookie or your browser's local
                storage depending on the sign-in method. There are no
                advertising cookies, no tracking pixels, and no analytics
                product on this site.
              </p>
            </Section>

            <Section title="How it is used">
              <p>
                Log data is used to operate, secure, and debug the site. Sign-in
                data is used to recognise an administrator account and to keep a
                session going. That is all. Nothing here feeds profiling or
                advertising.
              </p>
            </Section>

            <Section title="What is not done">
              <p>
                Your information is never sold, rented, or traded. It is not
                shared with anyone for their own marketing, and there is no
                third-party analytics or advertising code on these pages.
              </p>
            </Section>

            <Section title="Service providers">
              <p>
                The site runs on Amazon Web Services, which hosts it and stores
                the data described above on my behalf. Page fonts are served by
                Google Fonts, so loading a page requests those font files from
                Google. When an administrator chooses to sign in with GitHub or
                Google, that provider processes the sign-in under its own
                privacy policy.
              </p>
            </Section>

            <Section title="How long it is kept">
              <p>
                Server logs are deleted automatically after 7 days, or up to 14
                days for the test version of the site. The record of a failed
                sign-in attempt expires after 15 minutes. Account information
                for an administrator is kept until the account is deleted.
              </p>
            </Section>

            <Section title="Your choices">
              <p>
                You can ask to see the account information held about you, or
                ask for it to be deleted, by emailing{' '}
                <a
                  href={`mailto:${email}`}
                  className="text-accent-cyan-400 hover:text-accent-cyan-300 transition-colors"
                >
                  {email}
                </a>
                . You can also block cookies in your browser, though signing in
                will not work if you do.
              </p>
            </Section>

            <Section title="Children">
              <p>
                This site is not directed at children under 13, and information
                is not knowingly collected from them.
              </p>
            </Section>

            <Section title="Changes">
              <p>
                If this policy changes, the new wording and a new effective date
                will be posted on this page.
              </p>
            </Section>

            <Section title="Contact">
              <p>
                Questions about this policy can go to{' '}
                <a
                  href={`mailto:${email}`}
                  className="text-accent-cyan-400 hover:text-accent-cyan-300 transition-colors"
                >
                  {email}
                </a>
                .
              </p>
            </Section>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default Privacy;
