import type { UiLanguage } from '../config/phase0';
import { UI_MESSAGES, type MessageKey } from './messages';

export function t(
  language: UiLanguage,
  key: MessageKey,
  params?: Record<string, string | number>
): string {
  const template = UI_MESSAGES[language][key] ?? UI_MESSAGES.en[key];
  if (!params) {
    return template;
  }

  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    if (!(name in params)) {
      return match;
    }

    return String(params[name]);
  });
}