# ewt-gen

Generate static websites for ESPHome firmware distribution using ESP Web Tools.

## Quick Start

```bash
# From a local file
uvx ewt-gen config.yaml

# From a URL
uvx ewt-gen https://github.com/esphome/firmware/blob/main/esphome-web/esp32.factory.yaml
```

## Installation

```bash
# Run directly without installing (recommended)
uvx ewt-gen config.yaml

# Or install globally
uv tool install ewt-gen
ewt-gen config.yaml

# Or with pip
pip install ewt-gen
```

## Usage

```bash
# From a local file
uvx ewt-gen config.yaml

# From a GitHub file URL
uvx ewt-gen https://github.com/user/repo/blob/main/config.yaml

# From a GitHub Gist
uvx ewt-gen https://gist.github.com/user/abc123

# From any URL
uvx ewt-gen https://example.com/config.yaml
```

### Options

```
ewt-gen [OPTIONS] YAML_SOURCE

Options:
  --version                       Show version
  --skip-compile                  Skip ESPHome compilation (use existing firmware)
  -f, --firmware PATH             Path to firmware binary
  -c, --chip-family [esp32|esp32-c3|esp32-s2|esp32-s3|esp8266]
                                  Chip family (auto-detected from YAML)
  -o, --output PATH               Output directory (defaults to YAML filename)
  -t, --title TEXT                Page title (defaults to name from YAML)
  --pre-release                   Use pre-release ESPHome version via uvx
  --help                          Show help
```

### Examples

```bash
# Basic usage - compiles and generates site
ewt-gen my-device.yaml

# Custom output directory and title
ewt-gen my-device.yaml -o ./dist -t "My Smart Device"

# Use pre-release ESPHome
ewt-gen my-device.yaml --pre-release

# Skip compilation, use existing firmware
ewt-gen my-device.yaml --skip-compile -f firmware.bin
```

## Generated Site

The tool generates a static website containing:

- **ESP Web Tools install button** - One-click firmware installation (requires HTTPS)
- **Firmware download** - Direct download of the compiled binary
- **YAML download** - Original ESPHome configuration
- **Manual installation instructions** - For non-HTTPS contexts, with link to web.esphome.io

### HTTPS Requirement

Browser-based installation using ESP Web Tools requires a secure context (HTTPS or localhost). When served over HTTP, the page automatically shows manual installation instructions instead.

## ESPHome Detection

The tool automatically:

- Detects chip family from the YAML configuration
- Finds compiled firmware in `.esphome/build/` directory
- Uses local `esphome` if available, falls back to `uvx esphome`

## License

Apache 2.0

## Credits

- [ESP Web Tools](https://esphome.github.io/esp-web-tools/) - Browser-based firmware installation
- [ESPHome](https://esphome.io) - Easy ESP8266/ESP32 firmware configuration
- [Open Home Foundation](https://www.openhomefoundation.org/)
