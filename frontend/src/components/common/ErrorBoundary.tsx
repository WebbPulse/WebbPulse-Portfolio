import React, { Component } from 'react';
import { Link } from 'react-router-dom';

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

/**
 * Catches a render error below it and shows a recoverable fallback.
 *
 * Class based because React exposes error boundaries only through the lifecycle
 * methods. Sits inside the router so the fallback can link back to home.
 */
export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  override state: ErrorBoundaryState = { hasError: false };

  /** Flips to the fallback on the render pass that follows a thrown error. */
  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  override componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('Unhandled render error', error, errorInfo.componentStack);
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  override render(): React.ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="drawing-grid flex min-h-screen items-center justify-center px-4 text-ink">
        <div
          role="alert"
          className="relative w-full max-w-lg border border-line bg-paper-raised px-6 py-10 sm:px-10"
        >
          <p className="mono-label">Unexpected error</p>
          <h1 className="mt-4 text-3xl font-semibold tracking-[-0.02em] text-ink sm:text-4xl">
            Something went wrong
          </h1>
          <p className="mt-4 leading-relaxed text-ink-muted">
            This page hit an unexpected error. Reloading usually clears it.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={this.handleReload}
              className="inline-flex items-center justify-center border border-ink bg-ink px-5 py-3 text-sm font-medium text-paper transition-colors hover:border-accent hover:bg-accent"
            >
              Reload the page
            </button>
            <Link
              to="/"
              className="inline-flex items-center justify-center border border-line-strong px-5 py-3 text-sm font-medium text-ink transition-colors hover:border-ink"
            >
              Back to home
            </Link>
          </div>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
