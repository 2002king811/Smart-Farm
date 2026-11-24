import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from './locales/en.json';
import sw from './locales/sw.json';

export const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'sw', label: 'Kiswahili' },
] as const;

const LANG_KEY = 'sf.language';

function storedLanguage(): string {
  try {
    const v = window.localStorage.getItem(LANG_KEY);
    return v === 'sw' ? 'sw' : 'en';
  } catch {
    return 'en';
  }
}

/** Switch the interface language and remember it on this device. */
export function setLanguage(code: string) {
  const lang = code === 'sw' ? 'sw' : 'en';
  try {
    window.localStorage.setItem(LANG_KEY, lang);
  } catch {
    /* storage unavailable */
  }
  document.documentElement.lang = lang;
  void i18n.changeLanguage(lang);
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, sw: { translation: sw } },
  lng: storedLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

export default i18n;
