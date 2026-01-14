"""CLI interface for EWT."""

import shutil
import subprocess
from pathlib import Path

import click
import yaml

from ewt.generator import generate_site


@click.group()
@click.version_option()
def main():
    """EWT - Generate static websites for ESPHome firmware distribution."""
    pass


@main.command()
@click.argument("yaml_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--skip-compile",
    is_flag=True,
    help="Skip ESPHome compilation (use existing firmware).",
)
@click.option(
    "--firmware",
    "-f",
    type=click.Path(exists=True, path_type=Path),
    help="Path to firmware binary. If not specified, uses ESPHome build output.",
)
@click.option(
    "--chip-family",
    "-c",
    type=click.Choice(
        ["ESP32", "ESP32-C3", "ESP32-S2", "ESP32-S3", "ESP8266"],
        case_sensitive=False,
    ),
    help="Chip family. Auto-detected from YAML if not specified.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output directory. Defaults to YAML filename without extension.",
)
@click.option(
    "--title",
    "-t",
    help="Page title. Defaults to name from YAML file.",
)
@click.option(
    "--pre-release",
    is_flag=True,
    help="Use pre-release ESPHome version (uvx only, forces refresh).",
)
def generate(
    yaml_file: Path,
    skip_compile: bool,
    firmware: Path | None,
    chip_family: str | None,
    output: Path | None,
    title: str | None,
    pre_release: bool,
):
    """Generate a static website for firmware distribution.

    YAML_FILE is the ESPHome configuration file.
    """
    yaml_file = yaml_file.resolve()

    # Load YAML to get configuration info
    with open(yaml_file) as f:
        config = yaml.safe_load(f)

    # Determine project name
    esphome_config = config.get("esphome", {})
    project_name = esphome_config.get("name", yaml_file.stem)

    # Determine title
    if not title:
        title = esphome_config.get("friendly_name") or project_name

    # Compile with ESPHome if needed
    if not skip_compile and firmware is None:
        click.echo(f"Compiling {yaml_file.name} with ESPHome...")
        compile_with_esphome(yaml_file, pre_release=pre_release)

    # Find firmware binary
    if firmware is None:
        firmware = find_firmware(yaml_file, config)

    if firmware is None:
        raise click.ClickException(
            f"Could not find firmware binary. Please specify with --firmware option.\n"
            f"Looked for: {yaml_file.stem}.bin, .esphome/build/{project_name}/.pioenvs/*/firmware.bin"
        )

    firmware = firmware.resolve()

    # Determine chip family
    if chip_family is None:
        chip_family = detect_chip_family(config)

    if chip_family is None:
        raise click.ClickException(
            "Could not detect chip family from YAML. Please specify with --chip-family option."
        )

    # Normalize chip family
    chip_family = normalize_chip_family(chip_family)

    # Determine output directory
    if output is None:
        output = Path.cwd() / yaml_file.stem

    output = output.resolve()

    click.echo(f"Generating static site for {project_name}")
    click.echo(f"  YAML: {yaml_file}")
    click.echo(f"  Firmware: {firmware}")
    click.echo(f"  Chip: {chip_family}")
    click.echo(f"  Output: {output}")

    generate_site(
        output_dir=output,
        yaml_file=yaml_file,
        firmware_file=firmware,
        chip_family=chip_family,
        title=title,
    )

    click.echo(f"\nStatic site generated at: {output}")
    click.echo("Serve with any static file server (must be HTTPS for ESP Web Tools)")


def compile_with_esphome(yaml_file: Path, *, pre_release: bool = False) -> None:
    """Compile the ESPHome configuration."""
    if shutil.which("esphome") and not pre_release:
        cmd = ["esphome", "compile", str(yaml_file)]
    elif shutil.which("uvx"):
        cmd = ["uvx"]
        if pre_release:
            cmd += ["--prerelease", "allow", "--refresh"]
        cmd += ["esphome", "compile", str(yaml_file)]
    else:
        raise click.ClickException(
            "ESPHome not found. Please install ESPHome or uv:\n"
            "  pip install esphome\n"
            "Or use --skip-compile with --firmware to provide a pre-built binary."
        )

    try:
        subprocess.run(cmd, check=True, cwd=yaml_file.parent)
    except subprocess.CalledProcessError as e:
        raise click.ClickException(
            f"ESPHome compilation failed with exit code {e.returncode}"
        )


def find_firmware(yaml_file: Path, config: dict) -> Path | None:
    """Try to find the firmware binary for the given YAML file."""
    yaml_dir = yaml_file.parent

    # Try same name with .bin extension
    bin_file = yaml_dir / f"{yaml_file.stem}.bin"
    if bin_file.exists():
        return bin_file

    # Try ESPHome build directory
    esphome_config = config.get("esphome", {})
    project_name = esphome_config.get("name", yaml_file.stem)

    esphome_build_dir = yaml_dir / ".esphome" / "build" / project_name / ".pioenvs"
    if esphome_build_dir.exists():
        # Look for firmware.bin in any subdirectory
        for subdir in esphome_build_dir.iterdir():
            if subdir.is_dir():
                fw = subdir / "firmware.bin"
                if fw.exists():
                    return fw

    return None


def detect_chip_family(config: dict) -> str | None:
    """Try to detect chip family from ESPHome config."""
    # Check for esp32 platform
    if "esp32" in config:
        esp32_config = config["esp32"]
        board = esp32_config.get("board", "")
        variant = esp32_config.get("variant", "").upper()

        # Check variant first
        if variant:
            if variant in ("ESP32C3", "ESP32-C3"):
                return "ESP32-C3"
            if variant in ("ESP32S2", "ESP32-S2"):
                return "ESP32-S2"
            if variant in ("ESP32S3", "ESP32-S3"):
                return "ESP32-S3"

        # Check board names for variants
        board_lower = board.lower()
        if "c3" in board_lower:
            return "ESP32-C3"
        if "s2" in board_lower:
            return "ESP32-S2"
        if "s3" in board_lower:
            return "ESP32-S3"

        return "ESP32"

    # Check for esp8266 platform
    if "esp8266" in config:
        return "ESP8266"

    return None


def normalize_chip_family(chip_family: str) -> str:
    """Normalize chip family string."""
    mapping = {
        "esp32": "ESP32",
        "esp32c3": "ESP32-C3",
        "esp32-c3": "ESP32-C3",
        "esp32s2": "ESP32-S2",
        "esp32-s2": "ESP32-S2",
        "esp32s3": "ESP32-S3",
        "esp32-s3": "ESP32-S3",
        "esp8266": "ESP8266",
    }
    return mapping.get(chip_family.lower(), chip_family.upper())


if __name__ == "__main__":
    main()
