import React from 'react';
import {
  FaGithub,
  FaLinkedin,
  FaTwitter,
  FaInstagram,
  FaYoutube,
  FaDiscord,
  FaFacebook,
  FaReddit,
  FaStackOverflow,
  FaMedium,
  FaDev,
  FaBehance,
  FaDribbble,
  FaFigma,
  FaCodepen,
  FaGlobe,
} from 'react-icons/fa';
import { SiHashnode, SiSubstack } from 'react-icons/si';

/** Props for {@link SocialIcon}. */
export interface SocialIconProps {
  platform: string;
  className?: string;
  size?: number;
}

/** The brand icon for a social platform, by platform key. */
export const SocialIcon: React.FC<SocialIconProps> = ({
  platform,
  className = 'w-6 h-6',
  size = 24,
}) => {
  const iconMap: Record<string, React.ReactElement> = {
    github: <FaGithub className={className} size={size} />,
    linkedin: <FaLinkedin className={className} size={size} />,
    twitter: <FaTwitter className={className} size={size} />,
    instagram: <FaInstagram className={className} size={size} />,
    youtube: <FaYoutube className={className} size={size} />,
    discord: <FaDiscord className={className} size={size} />,
    facebook: <FaFacebook className={className} size={size} />,
    reddit: <FaReddit className={className} size={size} />,
    stackoverflow: <FaStackOverflow className={className} size={size} />,
    medium: <FaMedium className={className} size={size} />,
    dev: <FaDev className={className} size={size} />,
    hashnode: <SiHashnode className={className} size={size} />,
    substack: <SiSubstack className={className} size={size} />,
    behance: <FaBehance className={className} size={size} />,
    dribbble: <FaDribbble className={className} size={size} />,
    figma: <FaFigma className={className} size={size} />,
    codepen: <FaCodepen className={className} size={size} />,
    website: <FaGlobe className={className} size={size} />,
  };

  return (
    iconMap[platform.toLowerCase()] || (
      <FaGlobe className={className} size={size} />
    )
  );
};
