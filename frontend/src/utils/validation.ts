/** Reports whether a string looks like an email address. */
export const validateEmail = (email: string): boolean => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
};

/** Reports whether a value has non-whitespace content. */
export const validateRequired = (value: string): boolean => {
  return value.trim().length > 0;
};

/** Reports whether a string is at least `minLength` characters. */
export const validateMinLength = (
  value: string,
  minLength: number
): boolean => {
  return value.length >= minLength;
};

/** Reports whether a string is at most `maxLength` characters. */
export const validateMaxLength = (
  value: string,
  maxLength: number
): boolean => {
  return value.length <= maxLength;
};

/** Reports whether a string parses as a URL. */
export const validateUrl = (url: string): boolean => {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
};

/**
 * Applies a field's rules in order and returns the first failure message,
 * or null when the value passes every rule.
 */
export const getValidationError = (
  field: string,
  value: string,
  rules: {
    required?: boolean;
    email?: boolean;
    minLength?: number;
    maxLength?: number;
    url?: boolean;
  }
): string | null => {
  if (rules.required && !validateRequired(value)) {
    return `${field} is required`;
  }

  if (rules.email && value && !validateEmail(value)) {
    return `${field} must be a valid email address`;
  }

  if (rules.minLength && value && !validateMinLength(value, rules.minLength)) {
    return `${field} must be at least ${rules.minLength} characters`;
  }

  if (rules.maxLength && value && !validateMaxLength(value, rules.maxLength)) {
    return `${field} must be no more than ${rules.maxLength} characters`;
  }

  if (rules.url && value && !validateUrl(value)) {
    return `${field} must be a valid URL`;
  }

  return null;
};
