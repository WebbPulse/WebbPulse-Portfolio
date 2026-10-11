/** Styling and children props shared by the presentational components. */
export interface BaseComponentProps {
  className?: string;
  children?: React.ReactNode;
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
