# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ewt-gen is a Python CLI tool that generates static websites for ESPHome firmware distribution using ESP Web Tools. It compiles ESPHome configurations, extracts firmware binaries, and creates a ready-to-serve HTML site with browser-based installation support.

## Development Commands

```bash
# Run the tool (using uvx)
uvx ewt-gen config.yaml

# Run with options
uvx ewt-gen config.yaml --skip-compile -f firmware.bin -o output/

# Build package
uv build

# Install globally
uv tool install ewt-gen
```

## Architecture

The project follows a simple CLI + generation pattern:

```
src/ewt/
├── cli.py           # CLI entry point, main workflow orchestration
├── generator.py     # Static site generation (manifest, HTML, file copying)
├── __init__.py      # Package metadata
└── templates/
    └── index.html   # ESP Web Tools HTML template
```

### Code Flow

1. `cli.py::main()` - Entry point, parses CLI args
2. `resolve_yaml_source()` - Handles local files or URLs (GitHub, Gist support)
3. `load_esphome_yaml()` - Custom YAML loader that handles ESPHome tags (!lambda, !secret, etc.)
4. `expand_substitutions()` - Expands `${var}` variables in YAML
5. `compile_with_esphome()` - Runs `esphome compile` (local or via uvx)
6. `detect_chip_family()` - Auto-detects ESP32/ESP8266 variant from config
7. `generator.py::generate_site()` - Creates output directory with manifest.json, index.html, firmware.bin

### Key Patterns

- **YAML Parsing**: Uses custom `ESPHomeLoader` with multi-constructor to preserve ESPHome tags without executing them
- **Template Rendering**: Simple regex-based `{{ variable }}` substitution (not Jinja2)
- **Resource Loading**: Templates loaded via `importlib.resources` for proper package bundling
- **Chip Detection**: Heuristic extraction from esp32/esp8266 config sections

## Adding Features

- **New CLI option**: Add `@click.option()` decorator and parameter to `main()` in cli.py
- **Modify HTML output**: Edit `src/ewt/templates/index.html` - uses `{{ variable }}` syntax
- **Change manifest format**: Update `generate_manifest()` in generator.py
- **Add chip family support**: Extend `detect_chip_family()` in cli.py
