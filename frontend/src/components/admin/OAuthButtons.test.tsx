import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { OAuthButtons } from './OAuthButtons';

const ORIGIN = 'https://api.example.test';
const START = `${ORIGIN}/api/auth/oauth`;
/** The normalised shape the package hands a component. */
const GOOGLE = { id: 'google', displayName: 'Google' };
const GITHUB = { id: 'github', displayName: 'GitHub' };

describe('OAuthButtons', () => {
  it('renders nothing for an empty provider list', () => {
    const { container } = render(
      <OAuthButtons providers={[]} startUrl={(p) => `${START}/${p}/start`} />
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('renders a real link per provider, not a button', () => {
    render(
      <OAuthButtons
        providers={[GOOGLE, GITHUB]}
        startUrl={(p) => `${START}/${p}/start?return_to=%2Fadmin`}
      />
    );

    const google = screen.getByTestId('oauth-start-google');
    expect(google.tagName).toBe('A');
    expect(google).toHaveAttribute(
      'href',
      `${START}/google/start?return_to=%2Fadmin`
    );
    expect(screen.getByTestId('oauth-start-github')).toBeInTheDocument();
  });

  it('labels each button with the name the backend gave', () => {
    render(
      <OAuthButtons
        providers={[GOOGLE, GITHUB]}
        startUrl={(p) => `${START}/${p}/start`}
      />
    );

    expect(screen.getByText(/sign in with google/i)).toBeInTheDocument();
    expect(screen.getByText(/sign in with github/i)).toBeInTheDocument();
  });

  it('renders a provider this build has never heard of', () => {
    render(
      <OAuthButtons
        providers={[{ id: 'gitlab', displayName: 'GitLab' }]}
        startUrl={(p) => `${START}/${p}/start`}
      />
    );

    expect(screen.getByTestId('oauth-start-gitlab')).toHaveAttribute(
      'href',
      `${START}/gitlab/start`
    );
    expect(screen.getByText(/sign in with gitlab/i)).toBeInTheDocument();
  });
});
