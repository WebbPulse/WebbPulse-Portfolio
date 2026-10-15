import React from 'react';
import { PublicShell } from '../components/layout';
import { MonoLabel, Sheet } from '../components/drawing';
import { getSiteContent } from '../content';
import { useDocumentMeta } from '../hooks';

/** The date the current wording took effect, shown at the top of the page. */
const EFFECTIVE_DATE = 'October 10, 2026';

/** One numbered clause of the policy. */
const Section: React.FC<{
  index: number;
  title: string;
  children: React.ReactNode;
}> = ({ index, title, children }) => (
  <section className="grid gap-3 border-t border-line pt-6 sm:grid-cols-[4rem_1fr]">
    <span className="font-mono text-xs text-accent tabular-nums sm:pt-1.5">
      {String(index).padStart(2, '0')}
    </span>
    <div className="space-y-3">
      <h2 className="text-xl font-semibold tracking-tight text-ink">{title}</h2>
      <div className="space-y-3 leading-relaxed text-ink-muted">{children}</div>
    </div>
  </section>
);

/**
 * The public privacy policy.
 *
 * A plain public route because Google's OAuth consent screen requires a reachable
 * policy URL. Update the wording whenever the data handling changes.
 */
export const Privacy: React.FC = () => {
  useDocumentMeta({ title: 'Privacy' });
  const data = getSiteContent();
  const email = data.email ?? 'tyler@webbpulse.com';

  return (
    <PublicShell>
      <main id="main" className="flex-1" data-testid="page-privacy">
        <Sheet className="py-16 sm:py-24">
          <div className="mx-auto max-w-3xl">
            <header className="mb-12 border-b border-line-strong pb-8">
              <MonoLabel as="p">Policy</MonoLabel>
              <h1 className="mt-4 text-4xl font-semibold tracking-[-0.02em] text-ink sm:text-5xl">
                Privacy Policy
              </h1>
              <p className="mt-4 font-mono text-xs text-ink-muted">
                Effective {EFFECTIVE_DATE}
              </p>
            </header>

            <div className="space-y-10">
              <Section index={1} title="About this site">
                <p>
                  portfolio.webbpulse.com is the personal portfolio site of
                  Tyler Webb, a software engineer. It publishes writing and
                  project information. You can read every public page without
                  signing in and without giving me any personal information.
                </p>
              </Section>

              <Section index={2} title="What is collected">
                <p>
                  <strong className="text-ink">Server logs.</strong> The API
                  records ordinary request information: the IP address the
                  request came from, the time, the method and path, and the
                  response status. Browser user agents are not recorded. These
                  logs exist to keep the site running and to investigate errors
                  and abuse.
                </p>
                <p>
                  <strong className="text-ink">Sign-in data.</strong> Sign in is
                  for the site owner and administrators only. There is no public
                  sign up, so if you are reading this as a visitor, none of it
                  applies to you. An administrator account holds a username, an
                  email address, and whether the account is active and verified.
                </p>
                <p>
                  <strong className="text-ink">
                    Sign in with GitHub or Google.
                  </strong>{' '}
                  Administrators can sign in through GitHub or Google instead of
                  a password. When someone does, the provider returns the email
                  address on their account and the identifier it assigns to it,
                  and those are stored so the account can be recognised next
                  time. A password is never received from a provider.
                </p>
                <p>
                  <strong className="text-ink">Failed sign-ins.</strong> To slow
                  down password guessing, the IP address of a failed sign-in
                  attempt is recorded for 15 minutes and then deleted
                  automatically.
                </p>
                <p>
                  <strong className="text-ink">
                    Cookies and browser storage.
                  </strong>{' '}
                  If you switch between the light and dark themes, that choice
                  is saved in your browser&apos;s local storage and never leaves
                  your device. Apart from that, nothing is stored in your
                  browser until you sign in. Signing in keeps a session going,
                  using a cookie or your browser's local storage depending on
                  the sign-in method. There are no advertising cookies, no
                  tracking pixels, and no analytics product on this site.
                </p>
              </Section>

              <Section index={3} title="How it is used">
                <p>
                  Log data is used to operate, secure, and debug the site.
                  Sign-in data is used to recognise an administrator account and
                  to keep a session going. That is all. Nothing here feeds
                  profiling or advertising.
                </p>
              </Section>

              <Section index={4} title="What is not done">
                <p>
                  Your information is never sold, rented, or traded. It is not
                  shared with anyone for their own marketing, and there is no
                  third-party analytics or advertising code on these pages.
                </p>
              </Section>

              <Section index={5} title="Service providers">
                <p>
                  The site runs on Amazon Web Services, which hosts it and
                  stores the data described above on my behalf. Page fonts are
                  served from this site itself, so no font files are requested
                  from Google or any other third party. When an administrator
                  chooses to sign in with GitHub or Google, that provider
                  processes the sign-in under its own privacy policy.
                </p>
              </Section>

              <Section index={6} title="How long it is kept">
                <p>
                  Server logs are deleted automatically after 7 days, or up to
                  14 days for the test version of the site. The record of a
                  failed sign-in attempt expires after 15 minutes. Account
                  information for an administrator is kept until the account is
                  deleted.
                </p>
              </Section>

              <Section index={7} title="Your choices">
                <p>
                  You can ask to see the account information held about you, or
                  ask for it to be deleted, by emailing{' '}
                  <a href={`mailto:${email}`} className="ink-link">
                    {email}
                  </a>
                  . You can also block cookies in your browser, though signing
                  in will not work if you do.
                </p>
              </Section>

              <Section index={8} title="Children">
                <p>
                  This site is not directed at children under 13, and
                  information is not knowingly collected from them.
                </p>
              </Section>

              <Section index={9} title="Changes">
                <p>
                  If this policy changes, the new wording and a new effective
                  date will be posted on this page.
                </p>
              </Section>

              <Section index={10} title="Contact">
                <p>
                  Questions about this policy can go to{' '}
                  <a href={`mailto:${email}`} className="ink-link">
                    {email}
                  </a>
                  .
                </p>
              </Section>
            </div>
          </div>
        </Sheet>
      </main>
    </PublicShell>
  );
};

export default Privacy;
