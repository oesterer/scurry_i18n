#!/usr/bin/env python3
import argparse
import html
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOCALES_DIR = ROOT / "locales"
WEBSITE_DIR = ROOT / "website"

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


def normalize_entry(value):
    if isinstance(value, dict):
        return {"value": value.get("value", "")}
    return {"value": value}


def locale_value(entry):
    if isinstance(entry, dict):
        return entry.get("value", "")
    return entry


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


def load_locale(locale):
    path = LOCALES_DIR / f"{locale}.json"
    if not path.exists():
        raise SystemExit(f"Missing locale dictionary: {path}")
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def extract():
    LOCALES_DIR.mkdir(exist_ok=True)
    locale_path = LOCALES_DIR / "en_US.json"
    if locale_path.exists():
        entries = {
            key: normalize_entry(entry)
            for key, entry in json.loads(locale_path.read_text(encoding="utf-8")).items()
        }
    else:
        entries = {}
    text_to_key = {
        locale_value(entry): key
        for key, entry in entries.items()
        if locale_value(entry)
    }
    used_keys = set(entries)
    validate_key_lengths(entries)

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
                        entries[key] = {"value": value}
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
                    entries[key] = {"value": value}
                output.append(f"{leading}{{{{{key}}}}}{trailing}")
            else:
                output.append(part)

        path.write_text("".join(output), encoding="utf-8")

    locale_path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Extracted {len(entries)} strings to {locale_path}")


def render_template(template, dictionary, locale):
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
    return re.sub(r'(<html\s+[^>]*lang=)["\'][^"\']+["\']', rf'\1"{html_lang}"', rendered, count=1)


def copy_assets(target_dir):
    for item in ROOT.iterdir():
        if item.name.startswith("."):
            continue
        if item.name in {"website", "locales", "__pycache__"}:
            continue
        if item.name in HTML_FILES or item.name == "i18n.py":
            continue
        destination = target_dir / item.name
        if item.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(item, destination, ignore=shutil.ignore_patterns(".*", "__pycache__"))
        elif item.is_file():
            shutil.copy2(item, destination)


def build():
    WEBSITE_DIR.mkdir(exist_ok=True)
    for locale_path in sorted(LOCALES_DIR.glob("*.json")):
        locale = locale_path.stem
        dictionary = load_locale(locale)
        locale_dir = WEBSITE_DIR / locale
        if locale_dir.exists():
            shutil.rmtree(locale_dir)
        locale_dir.mkdir(parents=True, exist_ok=True)
        copy_assets(locale_dir)
        for file_name in HTML_FILES:
            source = ROOT / file_name
            if not source.exists():
                continue
            rendered = render_template(source.read_text(encoding="utf-8"), dictionary, locale)
            (locale_dir / file_name).write_text(rendered, encoding="utf-8")
        print(f"Generated {locale_dir}")


def main():
    parser = argparse.ArgumentParser(description="Extract and build localized static Scurry website files.")
    parser.add_argument("command", choices=("extract", "build"), help="extract English strings or build website output")
    args = parser.parse_args()
    if args.command == "extract":
        extract()
    else:
        build()


if __name__ == "__main__":
    main()
