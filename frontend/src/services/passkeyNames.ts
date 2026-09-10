/**
 * A default name for a new passkey, from what the platform will likely be.
 *
 * A guess, and deliberately a weak one: the browser tells a page nothing about
 * which authenticator the user is about to reach for, and a user with a phone
 * plugged into a laptop can enrol either. It is prefilled rather than imposed,
 * so the common case is one confirm and the uncommon one is a retype. The
 * server caps the label at 64 characters and substitutes `Passkey` for an
 * empty one, so no value here can be wrong enough to fail.
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
