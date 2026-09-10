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
