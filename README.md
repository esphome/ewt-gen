# ewt-gen

Generate static websites for ESPHome firmware distribution using ESP Web Tools.

## Quick Start

```bash
# From a local file
uvx ewt-gen config.yaml

# From a URL
uvx ewt-gen https://github.com/esphome/firmware/blob/main/esphome-web/esp32.factory.yaml

# Multiple configurations
uvx ewt-gen esp32.yaml esp32c3.yaml
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
  --publish-url TEXT              URL where firmware will be published (enables OTA)
  --fw-version TEXT               Firmware version (read from esphome.project.version if not specified)
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

# Enable OTA updates and dashboard import
ewt-gen my-device.yaml --publish-url https://firmware.example.com/my-device

# Specify version explicitly
ewt-gen my-device.yaml --publish-url https://firmware.example.com/my-device --fw-version 1.0.0
```

### OTA Updates and Dashboard Import

When using `--publish-url`, the tool generates a factory firmware that includes:

- **OTA updates via HTTP** - Devices can check for and install firmware updates
- **Dashboard import** - Users can adopt the device in ESPHome Dashboard (if source is a GitHub URL)

The tool creates two YAML files in the output:
- `{name}.yaml` - The original configuration (for users to customize)
- `{name}.factory.yaml` - Factory firmware that imports the original and adds OTA support

The version is required for OTA updates to work correctly. It can be specified via:
- `--fw-version` command line option
- `esphome.project.version` field in the YAML configuration

If no version is found, a warning is shown and OTA components are omitted (dashboard import still works).

## Generated Site

The tool generates a static website containing:

- **ESP Web Tools install button** - One-click firmware installation (requires HTTPS)
- **Alternative install section** - Link to download binary and use with ESPHome Web
- **ESPHome configuration section** - Download links and expandable view of the YAML configuration
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
