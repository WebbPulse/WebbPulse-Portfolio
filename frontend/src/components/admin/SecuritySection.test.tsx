import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

import { SecuritySection, type SecurityClient } from './SecuritySection';

function stubClient(overrides: Partial<SecurityClient> = {}): SecurityClient {
  return {
    enrolTotp: vi.fn(),
    activateTotp: vi.fn(),
    disableTotp: vi.fn(),
    regenerateRecoveryCodes: vi.fn(),
    ...overrides,
  };
}

/** A refusal in the shape the package's outcome union produces. */
function refusal(reason: string, message = '', retryAfter?: number) {
  return {
    ok: false as const,
    reason,
    message,
    code: undefined,
    ...(retryAfter === undefined ? {} : { retryAfter }),
  };
}

const ENROLMENT = {
  ok: true as const,
  secret: 'JBSWY3DPEHPK3PXP',
  provisioningUri:
    'otpauth://totp/WebbPulse:tyler@webbpulse.com?secret=JBSWY3DPEHPK3PXP&issuer=WebbPulse',
};

const CODES = ['AAAAA-BBBBB-CCCCC-DDDDD', 'EEEEE-FFFFF-GGGGG-HHHHH'];

/** Clicks the enrol button and waits for the scanning screen. */
async function startEnrolment(client: SecurityClient) {
  render(<SecuritySection client={client} />);
  fireEvent.click(
    screen.getByRole('button', { name: /set up an authenticator app/i })
  );
  await screen.findByTestId('totp-secret');
}

/** Types a code into the visible prompt and submits it. */
function submitCode(code: string, buttonName: RegExp) {
  fireEvent.change(screen.getByLabelText(/authenticator or recovery code/i), {
    target: { value: code },
  });
  fireEvent.click(screen.getByRole('button', { name: buttonName }));
}

describe('SecuritySection', () => {
  let writeText: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('enrolment sequence', () => {
    it('shows the secret and a QR code, then the recovery codes after activation', async () => {
      const client = stubClient({
        enrolTotp: vi.fn().mockResolvedValue(ENROLMENT),
        activateTotp: vi
          .fn()
          .mockResolvedValue({ ok: true, recoveryCodes: CODES }),
      });

      await startEnrolment(client);

      expect(screen.getByTestId('totp-secret')).toHaveTextContent(
        'JBSWY3DPEHPK3PXP'
      );
      expect(
        screen.getByRole('img', { name: /qr code for the authenticator app/i })
      ).toBeInTheDocument();
      expect(
        screen.getByRole('link', { name: /open the setup link/i })
      ).toHaveAttribute('href', ENROLMENT.provisioningUri);

      submitCode('123456', /turn on/i);

      await screen.findByTestId('recovery-codes');
      expect(client.activateTotp).toHaveBeenCalledWith({ code: '123456' });
      for (const code of CODES) {
        expect(screen.getByTestId('recovery-codes')).toHaveTextContent(code);
      }
      expect(screen.getByTestId('factor-status')).toHaveTextContent(
        /an authenticator app is set up/i
      );
    });

    it('keeps the recovery codes on screen until the user confirms saving them', async () => {
      const client = stubClient({
        enrolTotp: vi.fn().mockResolvedValue(ENROLMENT),
        activateTotp: vi
          .fn()
          .mockResolvedValue({ ok: true, recoveryCodes: CODES }),
      });

      await startEnrolment(client);
      submitCode('123456', /turn on/i);
      await screen.findByTestId('recovery-codes');

      const done = screen.getByRole('button', { name: /^done$/i });
      expect(done).toBeDisabled();

      fireEvent.click(screen.getByLabelText(/i have saved these codes/i));
      expect(done).not.toBeDisabled();

      fireEvent.click(done);
      await waitFor(() => {
        expect(screen.queryByTestId('recovery-codes')).not.toBeInTheDocument();
      });
    });

    it('trims the code before sending it', async () => {
      const client = stubClient({
        enrolTotp: vi.fn().mockResolvedValue(ENROLMENT),
        activateTotp: vi
          .fn()
          .mockResolvedValue({ ok: true, recoveryCodes: CODES }),
      });

      await startEnrolment(client);
      submitCode('  123456  ', /turn on/i);

      await waitFor(() => {
        expect(client.activateTotp).toHaveBeenCalledWith({ code: '123456' });
      });
    });

    it('copies the recovery codes as separate lines', async () => {
      const client = stubClient({
        enrolTotp: vi.fn().mockResolvedValue(ENROLMENT),
        activateTotp: vi
          .fn()
          .mockResolvedValue({ ok: true, recoveryCodes: CODES }),
      });

      await startEnrolment(client);
      submitCode('123456', /turn on/i);
      await screen.findByTestId('recovery-codes');

      fireEvent.click(screen.getByRole('button', { name: /copy codes/i }));
      await waitFor(() => {
        expect(writeText).toHaveBeenCalledWith(CODES.join('\n'));
      });
    });
  });

  describe('disable', () => {
    it('asks for a code first and reports the factor off', async () => {
      const client = stubClient({
        disableTotp: vi.fn().mockResolvedValue({ ok: true }),
      });
      render(<SecuritySection client={client} />);

      fireEvent.click(
        screen.getByRole('button', { name: /turn off the authenticator app/i })
      );
      expect(client.disableTotp).not.toHaveBeenCalled();

      submitCode('654321', /^turn off$/i);

      await waitFor(() => {
        expect(client.disableTotp).toHaveBeenCalledWith({ code: '654321' });
      });
      expect(await screen.findByRole('status')).toHaveTextContent(
        /recovery code for it is void/i
      );
      expect(screen.getByTestId('factor-status')).toHaveTextContent(
        /no authenticator app is set up/i
      );
    });
  });

  describe('regenerate', () => {
    it('asks for a code first, then shows the replacement set once', async () => {
      const client = stubClient({
        regenerateRecoveryCodes: vi
          .fn()
          .mockResolvedValue({ ok: true, recoveryCodes: CODES }),
      });
      render(<SecuritySection client={client} />);

      fireEvent.click(
        screen.getByRole('button', { name: /generate new recovery codes/i })
      );
      expect(client.regenerateRecoveryCodes).not.toHaveBeenCalled();

      submitCode('111111', /^generate$/i);

      await screen.findByTestId('recovery-codes');
      expect(client.regenerateRecoveryCodes).toHaveBeenCalledWith({
        code: '111111',
      });
      expect(screen.getByRole('button', { name: /^done$/i })).toBeDisabled();
    });
  });

  describe('refusals', () => {
    it('renders the server sentence for a rejected code', async () => {
      const client = stubClient({
        enrolTotp: vi.fn().mockResolvedValue(ENROLMENT),
        activateTotp: vi
          .fn()
          .mockResolvedValue(
            refusal('invalid-code', 'That code is not valid.')
          ),
      });

      await startEnrolment(client);
      submitCode('000000', /turn on/i);

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'That code is not valid.'
      );
      expect(screen.getByTestId('totp-secret')).toBeInTheDocument();
    });

    it('records the account as enabled when enrolment is already enabled', async () => {
      const client = stubClient({
        enrolTotp: vi.fn().mockResolvedValue(refusal('already-enabled')),
      });
      render(<SecuritySection client={client} />);

      fireEvent.click(
        screen.getByRole('button', { name: /set up an authenticator app/i })
      );

      expect(await screen.findByRole('alert')).toHaveTextContent(
        /already has an authenticator app/i
      );
      expect(screen.getByTestId('factor-status')).toHaveTextContent(
        /an authenticator app is set up/i
      );
    });

    it('explains a stale enrolment', async () => {
      const client = stubClient({
        enrolTotp: vi.fn().mockResolvedValue(ENROLMENT),
        activateTotp: vi
          .fn()
          .mockResolvedValue(refusal('no-pending-enrolment')),
      });

      await startEnrolment(client);
      submitCode('123456', /turn on/i);

      expect(await screen.findByRole('alert')).toHaveTextContent(
        /no longer pending/i
      );
    });

    it('adds the retry hint to a rate limit when the server sent one', async () => {
      const client = stubClient({
        disableTotp: vi.fn().mockResolvedValue(refusal('rate-limited', '', 90)),
      });
      render(<SecuritySection client={client} />);

      fireEvent.click(
        screen.getByRole('button', { name: /turn off the authenticator app/i })
      );
      submitCode('123456', /^turn off$/i);

      expect(await screen.findByRole('alert')).toHaveTextContent(
        /try again in 90 seconds/i
      );
    });

    it('reports an unavailable deployment', async () => {
      const client = stubClient({
        enrolTotp: vi.fn().mockResolvedValue(refusal('unavailable')),
      });
      render(<SecuritySection client={client} />);

      fireEvent.click(
        screen.getByRole('button', { name: /set up an authenticator app/i })
      );

      expect(await screen.findByRole('alert')).toHaveTextContent(
        /not available on this deployment/i
      );
      expect(screen.getByTestId('factor-status')).toHaveTextContent(
        /has no route that reports it/i
      );
    });

    it('turns a thrown error into a retry sentence rather than a crash', async () => {
      const client = stubClient({
        enrolTotp: vi.fn().mockRejectedValue(new Error('network down')),
      });
      render(<SecuritySection client={client} />);

      fireEvent.click(
        screen.getByRole('button', { name: /set up an authenticator app/i })
      );

      expect(await screen.findByRole('alert')).toHaveTextContent(
        /could not be completed/i
      );
    });
  });

  it('says it cannot report enrolment state before anything has happened', () => {
    render(<SecuritySection client={stubClient()} />);
    expect(screen.getByTestId('factor-status')).toHaveTextContent(
      /has no route that reports it/i
    );
  });
});
