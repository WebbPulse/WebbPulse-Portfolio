/**
 * A default name for a new passkey, guessed from the platform.
 *
 * Prefilled rather than imposed; the server caps the label and substitutes one
 * for an empty value, so no guess here can fail.
 */
export function defaultPasskeyName(
  userAgent: string = typeof navigator === 'undefined'
    ? ''
    : navigator.userAgent
): string {
  const agent = userAgent.toLowerCase();
  if (agent.includes('iphone')) return 'iPhone';
  if (agent.includes('ipad')) return 'iPad';
  if (agent.includes('android')) return 'Android device';
  if (agent.includes('mac os') || agent.includes('macintosh')) return 'Mac';
  if (agent.includes('windows')) return 'Windows Hello';
  if (agent.includes('linux')) return 'This device';
  return 'Passkey';
}
