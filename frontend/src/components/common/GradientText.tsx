import React from 'react';

interface GradientTextProps {
  as?: keyof React.JSX.IntrinsicElements;
  className?: string;
  animated?: boolean;
  children: React.ReactNode;
}

/** Text filled with the site's gradient. */
const GradientText: React.FC<GradientTextProps> = ({
  as: Tag = 'span',
  className = '',
  animated = false,
  children,
}) => {
  const Component = Tag as React.ElementType;
  return (
    <Component
      className={`${animated ? 'text-gradient-animated' : 'text-gradient'} ${className}`}
    >
      {children}
    </Component>
  );
};

export default GradientText;
