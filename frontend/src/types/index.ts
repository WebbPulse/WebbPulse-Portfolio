/** Styling and children props shared by the presentational components. */
export interface BaseComponentProps {
  className?: string;
  children?: React.ReactNode;
}

/** Props for the shared Button, covering its visual variants and sizes. */
export interface ButtonProps extends BaseComponentProps {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  onClick?: () => void;
  type?: 'button' | 'submit' | 'reset';
}

/** A header or footer link, marked external when it leaves the site. */
export interface NavigationItem {
  label: string;
  href: string;
  external?: boolean;
}

/** A social profile link and the icon key used to render it. */
export interface SocialLink {
  platform: string;
  url: string;
  icon: string;
}

/** Fields collected by the contact form. */
export interface ContactFormData {
  name: string;
  email: string;
  message: string;
}
