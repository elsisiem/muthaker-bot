from config import DEFAULT_LANGUAGE

_translations = {}
_current_lang = DEFAULT_LANGUAGE


def register_language(code: str, translations: dict):
    _translations[code] = translations


def get_language(code: str = None) -> dict:
    code = code or _current_lang
    if code not in _translations:
        code = DEFAULT_LANGUAGE
    return _translations.get(code, _translations.get(DEFAULT_LANGUAGE, {}))


def t(key: str, lang: str = None, **kwargs) -> str:
    translations = get_language(lang)
    text = translations.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def get_languages_list():
    return [("en", "English"), ("ar", "العربية"), ("fr", "Français"), ("ru", "Русский")]