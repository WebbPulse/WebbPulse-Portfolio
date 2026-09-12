import React, { Component } from 'react';
import { Link } from 'react-router-dom';
import Button from './Button';
import GradientText from './GradientText';

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
      <div className="min-h-screen flex items-center justify-center relative overflow-hidden px-6">
        <div className="absolute inset-0 bg-mesh-1 opacity-40 pointer-events-none" />

        <div
          role="alert"
          className="relative z-10 max-w-lg w-full text-center surface-glass rounded-2xl px-8 py-12"
        >
          <h1 className="font-display text-3xl sm:text-4xl font-bold text-surface-50 mb-4">
            <GradientText as="span">Something went wrong</GradientText>
          </h1>
          <p className="text-surface-300 leading-relaxed mb-8">
            This page hit an unexpected error. Reloading usually clears it.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Button variant="primary" onClick={this.handleReload}>
              Reload the page
            </Button>
            <Link to="/">
              <Button variant="outline" className="w-full sm:w-auto">
                Back to home
              </Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
