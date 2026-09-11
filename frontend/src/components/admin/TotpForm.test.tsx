import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TotpForm } from './TotpForm';

describe('TotpForm', () => {
  it('hands the trimmed code back to the caller', () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <TotpForm
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        loading={false}
        error={null}
      />
    );

    fireEvent.change(screen.getByLabelText(/authentication code/i), {
      target: { value: ' 123456 ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^verify$/i }));

    expect(onSubmit).toHaveBeenCalledWith('123456');
  });

  it('renders the error from a rejected code', () => {
    render(
      <TotpForm
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        loading={false}
        error="That code is not valid."
      />
    );

    expect(screen.getByRole('alert')).toHaveTextContent(
      'That code is not valid.'
    );
  });

  it('tells the user a recovery code goes in the same field', () => {
    // The server shape tests this input: six digits is tried as TOTP and
    // anything else as a recovery code, on this one route. A user locked out
    // of their app has no other way to learn that.
    render(
      <TotpForm
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        loading={false}
        error={null}
      />
    );

    expect(
      screen.getByText(/recovery codes here instead/i)
    ).toBeInTheDocument();
    // A numeric keypad would make a base32 recovery code untypable on a phone.
    expect(screen.getByLabelText(/authentication code/i)).toHaveAttribute(
      'inputmode',
      'text'
    );
  });

  it('lets the user back out to the sign in form', () => {
    const onCancel = vi.fn();
    render(
      <TotpForm
        onSubmit={vi.fn()}
        onCancel={onCancel}
        loading={false}
        error={null}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /back to sign in/i }));

    expect(onCancel).toHaveBeenCalled();
  });
});
