# Scurry Static Website Localization

This repository uses simple HTML templates plus JSON translation files to generate localized static versions of the website.

## Structure

```text
.
├── *.html
├── i18n.py
├── locales/
│   ├── translations.json
│   └── generated/
│       ├── en_US.json
│       └── es_MX.json
└── website/
    ├── en_US/
    └── es_MX/
```

## HTML Templates

The root-level HTML files are templates. User-facing text is replaced with placeholder keys:

```html
<h1>{{index.stablecoin_stack_for_emerging}}</h1>
```

The part before the dot is the page name. The part after the dot is a short content-based key.

## Translation Source

`locales/translations.json` is the editable source of truth. It keeps the original English text and Spanish translation next to each other:

```json
{
  "index.join_the_waitlist": {
    "en_US": "Join the waitlist",
    "es_MX": "Unirse a la lista de espera"
  }
}
```

Edit this file when changing or adding translations.

## Generated Locale Dictionaries

`locales/generated/*.json` files are generated from `locales/translations.json`.

Example:

```json
{
  "index.join_the_waitlist": {
    "value": "Join the waitlist"
  }
}
```

These files are used by the website builder. Do not edit them directly; edit `locales/translations.json` and regenerate them.

## Commands

Run commands from the repository root.

### Generate Locale Dictionaries

```sh
python3 i18n.py generate
```

This reads `locales/translations.json` and writes one generated dictionary per locale into `locales/generated/`.

### Build Website Output

```sh
python3 i18n.py build
```

This generates the localized websites into `website/<locale>/`.

For example:

```text
website/en_US/index.html
website/es_MX/index.html
```

Assets such as CSS, JavaScript, images, and favicon files are copied into each locale folder so each generated site can be served independently.

### Extract New English Text

```sh
python3 i18n.py extract
```

This scans the root-level HTML files for user-facing English text, replaces new text with template keys, and merges new entries into `locales/translations.json`.

Existing translations are preserved. New entries receive the English `en_US` value and empty values for other locales.

After extracting, fill in the missing translations in `locales/translations.json`, then run:

```sh
python3 i18n.py build
```

## Adding a New Locale

You can add a locale manually or use automated translation.

### Automated Initial Translation

Automated translation uses the OpenAI API. Set `OPENAI_API_KEY` before running the command:

```sh
export OPENAI_API_KEY="your-api-key"
```

Then add the locale:

```sh
python3 i18n.py add-locale fr_FR --target-language "French (France)"
```

This command:

- Reads English values from `en_US`.
- Adds `fr_FR` to every entry in `locales/translations.json`.
- Performs an initial automated translation.
- Regenerates `locales/generated/fr_FR.json`.

You can choose a different source locale:

```sh
python3 i18n.py add-locale pt_BR --target-language "Portuguese (Brazil)" --source-locale es_MX
```

You can choose a model with `--model` or the `OPENAI_TRANSLATION_MODEL` environment variable:

```sh
OPENAI_TRANSLATION_MODEL="gpt-4o-mini" python3 i18n.py add-locale de_DE --target-language "German (Germany)"
```

If the locale already has values, use `--overwrite` to replace them:

```sh
python3 i18n.py add-locale fr_FR --target-language "French (France)" --overwrite
```

Review automated translations before publishing.

### Manual Locale Addition

Add the new locale code to each entry in `locales/translations.json`:

```json
{
  "index.join_the_waitlist": {
    "en_US": "Join the waitlist",
    "es_MX": "Unirse a la lista de espera",
    "pt_BR": "Entrar na lista de espera"
  }
}
```

Then run:

```sh
python3 i18n.py build
```

The output will be generated at:

```text
website/pt_BR/
```

## Key Rules

- Keys must match placeholders in the HTML templates.
- Keys use the format `page.short_content_key`.
- The part after the page name should be no more than 30 characters.
- Avoid HTML-specific key names such as `h1`, `p`, `title`, or `alt`.
- Keep `locales/translations.json` as the editable source of truth.
- Treat `locales/generated/` and `website/` as generated output.
