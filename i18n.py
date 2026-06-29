#!/usr/bin/env python3
import argparse
import fnmatch
import html
import json
import os
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOCALES_DIR = ROOT / "locales"
TRANSLATIONS_PATH = LOCALES_DIR / "translations.json"
GENERATED_LOCALES_DIR = LOCALES_DIR / "generated"
WEBSITE_DIR = ROOT / "website"
ALWAYS_EXCLUDE_FROM_WEBSITE = {"README.md", "blog_sources", "resume.sh"}
DEFAULT_LOCALE = "en_US"
LOCALE_LABELS = {
    "en_US": "English",
    "es_MX": "Español",
}

HTML_FILES = sorted(path.name for path in ROOT.glob("*.html"))

TRANSLATABLE_ATTRS = ("aria-label", "alt", "content", "placeholder", "title")
CONTENT_META_NAMES = {"description"}
SKIP_TEXT_PARENTS = {"script", "style"}
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}")
TAG_RE = re.compile(r"(<[^>]+>)")
ATTR_RE = re.compile(
    r"""(?P<name>aria-label|alt|content|placeholder|title)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.IGNORECASE | re.DOTALL,
)
TAG_NAME_RE = re.compile(r"^<\s*/?\s*([A-Za-z0-9:-]+)")
META_NAME_RE = re.compile(r"""name\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def slugify(value):
    value = html.unescape(value).strip().lower()
    value = value.replace("&", " and ")
    value = value.replace("+", " plus ")
    value = value.replace("%", " pct ")
    value = value.replace("$", " usd ")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:30].rstrip("_") or "text"


def is_placeholder(value):
    return bool(PLACEHOLDER_RE.fullmatch(value.strip()))


def should_translate_text(value):
    stripped = value.strip()
    if not stripped or is_placeholder(stripped):
        return False
    return bool(re.search(r"[A-Za-z]", stripped))


def should_translate_attr(tag, attr_name, value):
    if not should_translate_text(value):
        return False
    attr_name = attr_name.lower()
    tag_name_match = TAG_NAME_RE.match(tag)
    tag_name = tag_name_match.group(1).lower() if tag_name_match else ""
    if attr_name == "content":
        if tag_name != "meta":
            return False
        meta_name = META_NAME_RE.search(tag)
        return bool(meta_name and meta_name.group(1).lower() in CONTENT_META_NAMES)
    return attr_name in TRANSLATABLE_ATTRS


def make_key(page_stem, value, used_keys):
    base = slugify(value)
    key = f"{page_stem}.{base}"
    index = 2
    while key in used_keys:
        suffix = f"_{index}"
        stem = base[: 30 - len(suffix)].rstrip("_") or "text"
        key = f"{page_stem}.{stem}{suffix}"
        index += 1
    used_keys.add(key)
    return key


def validate_key_lengths(entries):
    too_long = [key for key in entries if "." in key and len(key.split(".", 1)[1]) > 30]
    if too_long:
        raise SystemExit(f"Keys exceed 30 characters after page name: {', '.join(too_long[:5])}")


def legacy_make_key(page_stem, context, value, used_keys):
    base = f"{page_stem}.{context}.{slugify(value)}"
    key = base
    index = 2
    while key in used_keys:
        key = f"{base}_{index}"
        index += 1
    used_keys.add(key)
    return key


def load_translations():
    if TRANSLATIONS_PATH.exists():
        with TRANSLATIONS_PATH.open(encoding="utf-8") as file:
            return json.load(file)
    legacy_files = sorted(
        path for path in LOCALES_DIR.glob("*.json") if path.name != TRANSLATIONS_PATH.name
    )
    translations = {}
    for path in legacy_files:
        locale = path.stem
        with path.open(encoding="utf-8") as file:
            dictionary = json.load(file)
        for key, entry in dictionary.items():
            value = entry.get("value", "") if isinstance(entry, dict) else entry
            translations.setdefault(key, {})[locale] = value
    return translations


def save_translations(translations):
    validate_key_lengths(translations)
    LOCALES_DIR.mkdir(exist_ok=True)
    TRANSLATIONS_PATH.write_text(
        json.dumps(translations, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def available_locales(translations):
    locales = set()
    for values in translations.values():
        locales.update(values)
    return sorted(locales)


def generate_locale_files(translations):
    GENERATED_LOCALES_DIR.mkdir(parents=True, exist_ok=True)
    locales = available_locales(translations)
    for locale in locales:
        dictionary = {
            key: {"value": values.get(locale, "")}
            for key, values in translations.items()
        }
        (GENERATED_LOCALES_DIR / f"{locale}.json").write_text(
            json.dumps(dictionary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return locales


def translate_batch_with_openai(source_values, source_locale, target_language, model):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required for automated translation.")

    system_prompt = (
        "You are a professional website localizer. Translate the JSON values from "
        f"{source_locale} into {target_language}. Return only a valid JSON object "
        "with exactly the same keys. Preserve brand names, product names, URLs, "
        "email addresses, numbers, currency symbols, and stablecoin terminology "
        "unless a standard local equivalent is clearly appropriate."
    )
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(source_values, ensure_ascii=False, indent=2),
            },
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"OpenAI translation request failed: {error.code} {details}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"OpenAI translation request failed: {error.reason}") from error

    try:
        content = data["choices"][0]["message"]["content"]
        translated = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as error:
        raise SystemExit("OpenAI translation response did not contain a valid JSON object.") from error

    missing = set(source_values) - set(translated)
    extra = set(translated) - set(source_values)
    if missing or extra:
        raise SystemExit(
            "OpenAI translation response keys did not match the request. "
            f"Missing: {sorted(missing)[:5]} Extra: {sorted(extra)[:5]}"
        )
    return {key: str(value) for key, value in translated.items()}


def add_locale(locale, target_language, source_locale, model, batch_size, overwrite):
    translations = load_translations()
    if not translations:
        raise SystemExit(f"No translations found at {TRANSLATIONS_PATH}")
    if not target_language:
        raise SystemExit("--target-language is required.")
    if batch_size < 1:
        raise SystemExit("--batch-size must be at least 1.")

    existing_values = [values.get(locale, "") for values in translations.values()]
    if any(existing_values) and not overwrite:
        raise SystemExit(f"{locale} already has translations. Use --overwrite to replace them.")

    keys = list(translations)
    translated_count = 0
    for start in range(0, len(keys), batch_size):
        batch_keys = keys[start : start + batch_size]
        source_values = {
            key: translations[key].get(source_locale, "")
            for key in batch_keys
            if translations[key].get(source_locale, "")
        }
        translated_values = translate_batch_with_openai(
            source_values,
            source_locale,
            target_language,
            model,
        ) if source_values else {}
        for key in batch_keys:
            translations[key][locale] = translated_values.get(key, "")
        translated_count += len(translated_values)
        print(f"Translated {translated_count}/{len(keys)} entries into {locale}")

    save_translations(translations)
    generate_locale_files(translations)
    print(f"Added {locale} to {TRANSLATIONS_PATH}")


def load_locale(locale):
    path = GENERATED_LOCALES_DIR / f"{locale}.json"
    if not path.exists():
        raise SystemExit(f"Missing locale dictionary: {path}")
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def extract():
    LOCALES_DIR.mkdir(exist_ok=True)
    translations = load_translations()
    entries = {
        key: values.get("en_US", "")
        for key, values in translations.items()
    }
    text_to_key = {
        value: key
        for key, value in entries.items()
        if value
    }
    used_keys = set(entries)
    validate_key_lengths(entries)
    locales = available_locales(translations) or ["en_US"]
    if "en_US" not in locales:
        locales.insert(0, "en_US")

    for file_name in HTML_FILES:
        path = ROOT / file_name
        if not path.exists():
            continue
        page_stem = path.stem.replace("-", "_")
        parts = TAG_RE.split(path.read_text(encoding="utf-8"))
        tag_stack = []
        output = []

        for part in parts:
            if not part:
                continue
            if part.startswith("<") and part.endswith(">"):
                tag_name_match = TAG_NAME_RE.match(part)
                tag_name = tag_name_match.group(1).lower() if tag_name_match else ""

                def replace_attr(match):
                    name = match.group("name")
                    quote = match.group("quote")
                    value = html.unescape(match.group("value").strip())
                    if not should_translate_attr(part, name, value):
                        return match.group(0)
                    key = text_to_key.get(value)
                    if not key:
                        key = make_key(page_stem, value, used_keys)
                        text_to_key[value] = key
                        translations[key] = {
                            locale: value if locale == "en_US" else ""
                            for locale in locales
                        }
                    return f'{name}={quote}{{{{{key}}}}}{quote}'

                output.append(ATTR_RE.sub(replace_attr, part))

                if tag_name and not part.startswith("</") and not part.endswith("/>"):
                    tag_stack.append(tag_name)
                elif tag_name and part.startswith("</"):
                    for i in range(len(tag_stack) - 1, -1, -1):
                        if tag_stack[i] == tag_name:
                            del tag_stack[i:]
                            break
                continue

            if tag_stack and tag_stack[-1] in SKIP_TEXT_PARENTS:
                output.append(part)
                continue

            if should_translate_text(part):
                leading = part[: len(part) - len(part.lstrip())]
                trailing = part[len(part.rstrip()) :]
                value = html.unescape(part.strip())
                key = text_to_key.get(value)
                if not key:
                    key = make_key(page_stem, value, used_keys)
                    text_to_key[value] = key
                    translations[key] = {
                        locale: value if locale == "en_US" else ""
                        for locale in locales
                    }
                output.append(f"{leading}{{{{{key}}}}}{trailing}")
            else:
                output.append(part)

        path.write_text("".join(output), encoding="utf-8")

    save_translations(translations)
    generate_locale_files(translations)
    print(f"Extracted {len(translations)} strings to {TRANSLATIONS_PATH}")


def locale_label(locale):
    return LOCALE_LABELS.get(locale, locale.replace("_", "-"))


def output_dir_for_locale(locale):
    if locale == DEFAULT_LOCALE:
        return WEBSITE_DIR
    return WEBSITE_DIR / locale


def relative_page_href(from_locale, to_locale, file_name):
    if from_locale == to_locale:
        return file_name
    if from_locale == DEFAULT_LOCALE:
        return f"{to_locale}/{file_name}"
    if to_locale == DEFAULT_LOCALE:
        return f"../{file_name}"
    return f"../{to_locale}/{file_name}"


def absolute_page_href(locale, file_name):
    site_base_url = os.environ.get("SITE_BASE_URL", "").rstrip("/")
    if locale == DEFAULT_LOCALE:
        path = file_name
    else:
        path = f"{locale}/{file_name}"
    if not site_base_url:
        return path
    return f"{site_base_url}/{path}"


def alternate_page_href(from_locale, to_locale, file_name):
    if os.environ.get("SITE_BASE_URL", "").rstrip("/"):
        return absolute_page_href(to_locale, file_name)
    return relative_page_href(from_locale, to_locale, file_name)


def locale_head_tags(current_locale, locales, file_name):
    tags = []
    for locale in locales:
        html_lang = locale.replace("_", "-")
        href = html.escape(alternate_page_href(current_locale, locale, file_name), quote=True)
        tags.append(f'  <link rel="alternate" hreflang="{html_lang}" href="{href}">')
    default_href = html.escape(alternate_page_href(current_locale, DEFAULT_LOCALE, file_name), quote=True)
    tags.append(f'  <link rel="alternate" hreflang="x-default" href="{default_href}">')
    tags.append(f'  <meta property="og:locale" content="{current_locale}">')
    for locale in locales:
        if locale != current_locale:
            tags.append(f'  <meta property="og:locale:alternate" content="{locale}">')
    return "\n".join(tags)


def inject_locale_head_tags(rendered, current_locale, locales, file_name):
    tags = locale_head_tags(current_locale, locales, file_name)
    return rendered.replace("</head>", f"{tags}\n</head>", 1)


def render_language_switcher(current_locale, locales, file_name):
    links = []
    for locale in locales:
        if locale == current_locale:
            continue
        html_lang = locale.replace("_", "-")
        label = html.escape(locale_label(locale))
        href = html.escape(relative_page_href(current_locale, locale, file_name))
        links.append(f'<a href="{href}" hreflang="{html_lang}" lang="{html_lang}">{label}</a>')
    if not links:
        return ""
    return (
        '<div class="language-switcher" aria-label="Language options">'
        + "".join(links)
        + "</div>"
    )


def inject_language_switcher(rendered, current_locale, locales, file_name):
    switcher = render_language_switcher(current_locale, locales, file_name)
    if not switcher:
        return rendered
    return rendered.replace("</nav>", f"{switcher}\n      </nav>", 1)


def render_template(template, dictionary, locale, locales, file_name):
    def replace(match):
        key = match.group(1)
        entry = dictionary.get(key)
        if entry is None:
            raise KeyError(f"Missing translation key '{key}'")
        if isinstance(entry, dict):
            return str(entry.get("value", ""))
        return str(entry)

    rendered = PLACEHOLDER_RE.sub(replace, template)
    html_lang = locale.replace("_", "-")
    rendered = re.sub(r'(<html\s+[^>]*lang=)["\'][^"\']+["\']', rf'\1"{html_lang}"', rendered, count=1)
    rendered = inject_locale_head_tags(rendered, locale, locales, file_name)
    return inject_language_switcher(rendered, locale, locales, file_name)


def load_gitignore_patterns():
    gitignore_path = ROOT / ".gitignore"
    if not gitignore_path.exists():
        return []
    patterns = []
    for line in gitignore_path.read_text(encoding="utf-8").splitlines():
        pattern = line.strip()
        if not pattern or pattern.startswith("#") or pattern.startswith("!"):
            continue
        patterns.append(pattern)
    return patterns


def is_gitignored(path, patterns):
    relative = path.relative_to(ROOT).as_posix()
    name = path.name
    for pattern in patterns:
        normalized = pattern.strip("/")
        if not normalized:
            continue
        if pattern.endswith("/") and (relative == normalized or relative.startswith(f"{normalized}/")):
            return True
        if "/" in normalized:
            if fnmatch.fnmatch(relative, normalized):
                return True
        elif fnmatch.fnmatch(name, normalized):
            return True
    return False


def should_copy_asset(path, gitignore_patterns):
    if path.name.startswith("."):
        return False
    if path.name in ALWAYS_EXCLUDE_FROM_WEBSITE:
        return False
    if path.name in {"website", "locales", "__pycache__"}:
        return False
    if path.name in HTML_FILES or path.name == "i18n.py":
        return False
    return not is_gitignored(path, gitignore_patterns)


def copy_assets(target_dir):
    gitignore_patterns = load_gitignore_patterns()
    for item in ROOT.iterdir():
        if not should_copy_asset(item, gitignore_patterns):
            continue
        destination = target_dir / item.name
        if item.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(
                item,
                destination,
                ignore=lambda directory, names: [
                    name
                    for name in names
                    if not should_copy_asset(Path(directory) / name, gitignore_patterns)
                ],
            )
        elif item.is_file():
            shutil.copy2(item, destination)


def clean_website_output(locales):
    WEBSITE_DIR.mkdir(exist_ok=True)
    gitignore_patterns = load_gitignore_patterns()
    default_files = set(HTML_FILES)
    for item in ROOT.iterdir():
        if should_copy_asset(item, gitignore_patterns):
            default_files.add(item.name)
    expected_top_level = default_files | {locale for locale in locales if locale != DEFAULT_LOCALE}

    for item in WEBSITE_DIR.iterdir():
        if (
            item.name.startswith(".")
            or is_gitignored(item, gitignore_patterns)
            or item.name not in expected_top_level
        ):
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    for name in default_files:
        path = WEBSITE_DIR / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    for locale in locales:
        locale_dir = WEBSITE_DIR / locale
        if locale_dir.exists() and locale_dir.is_dir():
            shutil.rmtree(locale_dir)


def build():
    translations = load_translations()
    locales = generate_locale_files(translations)
    clean_website_output(locales)
    for locale in locales:
        dictionary = load_locale(locale)
        locale_dir = output_dir_for_locale(locale)
        if locale_dir.exists():
            if locale != DEFAULT_LOCALE:
                shutil.rmtree(locale_dir)
        locale_dir.mkdir(parents=True, exist_ok=True)
        copy_assets(locale_dir)
        for file_name in HTML_FILES:
            source = ROOT / file_name
            if not source.exists():
                continue
            rendered = render_template(source.read_text(encoding="utf-8"), dictionary, locale, locales, file_name)
            (locale_dir / file_name).write_text(rendered, encoding="utf-8")
        print(f"Generated {locale_dir}")


def main():
    parser = argparse.ArgumentParser(description="Extract and build localized static Scurry website files.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("extract", help="extract English strings into translations.json")
    subparsers.add_parser("generate", help="generate locale dictionaries from translations.json")
    subparsers.add_parser("build", help="build localized website output")
    add_locale_parser = subparsers.add_parser(
        "add-locale",
        help="add a locale to translations.json using automated translation",
    )
    add_locale_parser.add_argument("locale", help="Locale code to add, such as fr_FR or pt_BR")
    add_locale_parser.add_argument(
        "--target-language",
        required=True,
        help='Human-readable target language, such as "French (France)"',
    )
    add_locale_parser.add_argument(
        "--source-locale",
        default="en_US",
        help="Source locale to translate from, default: en_US",
    )
    add_locale_parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_TRANSLATION_MODEL", "gpt-4o-mini"),
        help="OpenAI model to use, default: OPENAI_TRANSLATION_MODEL or gpt-4o-mini",
    )
    add_locale_parser.add_argument(
        "--batch-size",
        type=int,
        default=40,
        help="Number of strings to translate per API call, default: 40",
    )
    add_locale_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing values for the locale if present",
    )
    args = parser.parse_args()
    if args.command == "extract":
        extract()
    elif args.command == "generate":
        translations = load_translations()
        locales = generate_locale_files(translations)
        print(f"Generated locale dictionaries: {', '.join(locales)}")
    elif args.command == "add-locale":
        add_locale(
            args.locale,
            args.target_language,
            args.source_locale,
            args.model,
            args.batch_size,
            args.overwrite,
        )
    else:
        build()


if __name__ == "__main__":
    main()
