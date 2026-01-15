"""CLI interface for EWT."""

import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import click
import yaml

from ewt.generator import generate_site


@click.command()
@click.version_option(package_name="ewt-gen")
@click.argument("yaml_source")
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
@click.option(
    "--publish-url",
    help="URL where the firmware will be published. Adds OTA updates and dashboard import.",
)
@click.option(
    "--fw-version",
    "fw_version",
    help="Firmware version. Read from esphome.project.version if not specified.",
)
def main(
    yaml_source: str,
    skip_compile: bool,
    firmware: Path | None,
    chip_family: str | None,
    output: Path | None,
    title: str | None,
    pre_release: bool,
    publish_url: str | None,
    fw_version: str | None,
):
    """Generate a static website for firmware distribution.

    YAML_SOURCE is the ESPHome configuration file path or URL.
    """
    yaml_file, temp_dir = resolve_yaml_source(yaml_source)

    # Load YAML to get configuration info (with ESPHome tag support)
    with open(yaml_file) as f:
        config = load_esphome_yaml(f)

    # Get substitutions for variable expansion
    substitutions = config.get("substitutions", {})

    def expand_substitutions(value: str) -> str:
        """Expand ${var} substitutions in a string."""
        if not isinstance(value, str):
            return value
        for key, sub_value in substitutions.items():
            value = value.replace(f"${{{key}}}", str(sub_value))
        return value

    # Determine project name
    esphome_config = config.get("esphome", {})
    project_name = expand_substitutions(esphome_config.get("name", "")) or yaml_file.stem

    # Determine title
    if not title:
        title = expand_substitutions(esphome_config.get("friendly_name", "")) or project_name

    # Determine version
    version = fw_version
    if version is None:
        project_config = esphome_config.get("project", {})
        version = expand_substitutions(project_config.get("version", ""))
        if not version:
            version = None

    # If publish_url is provided, create a modified YAML with OTA components
    compile_yaml_file = yaml_file
    if publish_url:
        # Convert source URL to github:// format for dashboard_import
        package_import_url = None
        if yaml_source.startswith(("http://", "https://")):
            package_import_url = convert_to_esphome_github_url(yaml_source)

        # Warn if no version - OTA updates won't work without it
        if version is None:
            click.secho(
                "Warning: No version found. OTA updates will not be included.\n"
                "Specify --fw-version or add esphome.project.version to your YAML.",
                fg="yellow",
                err=True,
            )

        compile_yaml_file = create_factory_yaml(
            yaml_file=yaml_file,
            publish_url=publish_url,
            package_import_url=package_import_url,
            version=version,
        )
        if version:
            click.echo(f"Added OTA update support (publish URL: {publish_url})")
        else:
            click.echo(f"Added dashboard import (publish URL: {publish_url})")

    # Compile with ESPHome if needed
    if not skip_compile and firmware is None:
        click.echo(f"Compiling {compile_yaml_file.name} with ESPHome...")
        compile_with_esphome(compile_yaml_file, pre_release=pre_release)

    # Find firmware binary
    if firmware is None:
        firmware = find_firmware(yaml_file, project_name)

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
    click.echo(f"  YAML: {compile_yaml_file}")
    click.echo(f"  Firmware: {firmware}")
    click.echo(f"  Chip: {chip_family}")
    click.echo(f"  Output: {output}")

    generate_site(
        output_dir=output,
        yaml_file=compile_yaml_file,
        firmware_file=firmware,
        chip_family=chip_family,
        title=title,
        original_yaml_file=yaml_file if publish_url else None,
        version=version,
    )

    # Clean up temp directory (YAML is already copied to output)
    if temp_dir is not None:
        shutil.rmtree(temp_dir)

    click.echo(f"\nStatic site generated at: {output}")
    click.echo("Serve with any static file server (must be HTTPS for ESP Web Tools)")


def load_esphome_yaml(stream):
    """Load ESPHome YAML with support for custom tags like !lambda, !secret, etc."""
    class ESPHomeLoader(yaml.SafeLoader):
        pass

    # Handle all unknown tags by returning the value as-is
    def constructor_undefined(loader, tag_suffix, node):
        if isinstance(node, yaml.ScalarNode):
            return loader.construct_scalar(node)
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node)

    ESPHomeLoader.add_multi_constructor("!", constructor_undefined)

    return yaml.load(stream, Loader=ESPHomeLoader)


def resolve_yaml_source(source: str) -> tuple[Path, Path | None]:
    """Resolve a YAML source (file path or URL) to a local file path.

    Returns (path, temp_dir) tuple. temp_dir is set if the source was downloaded
    and should be cleaned up after use.
    """
    # Check if it's a URL
    if source.startswith(("http://", "https://")):
        return download_yaml(source)

    # It's a local file path
    path = Path(source)
    if not path.exists():
        raise click.ClickException(f"File not found: {source}")
    return path.resolve(), None


def download_yaml(url: str) -> tuple[Path, Path]:
    """Download YAML from a URL and save to a temporary directory.

    Returns (yaml_path, temp_dir) tuple. The temp_dir should be cleaned up after use.
    """
    # Convert GitHub blob URLs to raw URLs
    url = convert_to_raw_url(url)

    click.echo(f"Downloading {url}...")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ewt"})
        with urllib.request.urlopen(req) as response:
            content = response.read().decode("utf-8")
    except urllib.error.URLError as e:
        raise click.ClickException(f"Failed to download {url}: {e}")

    # Extract filename from URL
    parsed = urlparse(url)
    filename = Path(parsed.path).name
    if not filename.endswith((".yaml", ".yml")):
        filename = "config.yaml"

    # Create temp directory for YAML and .esphome cache
    temp_dir = Path(tempfile.mkdtemp(prefix="ewt-"))
    yaml_file = temp_dir / filename
    yaml_file.write_text(content)

    return yaml_file, temp_dir


def convert_to_raw_url(url: str) -> str:
    """Convert GitHub/Gist URLs to raw content URLs."""
    # GitHub blob URL: https://github.com/user/repo/blob/branch/path/file.yaml
    # -> https://raw.githubusercontent.com/user/repo/branch/path/file.yaml
    github_blob = re.match(
        r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)", url
    )
    if github_blob:
        user, repo, branch, path = github_blob.groups()
        return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"

    # GitHub Gist URL: https://gist.github.com/user/gist_id
    # or https://gist.github.com/user/gist_id#file-filename-yaml
    # -> https://gist.githubusercontent.com/user/gist_id/raw/filename.yaml
    gist_match = re.match(
        r"https://gist\.github\.com/([^/]+)/([^/#]+)(?:#file-(.+))?", url
    )
    if gist_match:
        user, gist_id, file_fragment = gist_match.groups()
        if file_fragment:
            # Convert file-name-yaml to name.yaml
            filename = file_fragment.replace("-", ".")
            # Fix double dots from extension
            filename = re.sub(r"\.([^.]+)$", lambda m: "." + m.group(1), filename)
            return f"https://gist.githubusercontent.com/{user}/{gist_id}/raw/{filename}"
        return f"https://gist.githubusercontent.com/{user}/{gist_id}/raw"

    # Already a raw URL or other URL, return as-is
    return url


def compile_with_esphome(yaml_file: Path, *, pre_release: bool = False) -> None:
    """Compile the ESPHome configuration."""
    cwd = yaml_file.parent

    # If pre-release requested, must use uvx
    if pre_release:
        if not shutil.which("uvx"):
            raise click.ClickException(
                "uvx not found. Please install uv to use --pre-release."
            )
        cmd = ["uvx", "--prerelease", "allow", "--refresh", "esphome", "compile", str(yaml_file)]
    else:
        # Try local esphome first, fall back to uvx
        if shutil.which("esphome"):
            cmd = ["esphome", "compile", str(yaml_file)]
        elif shutil.which("uvx"):
            cmd = ["uvx", "esphome", "compile", str(yaml_file)]
        else:
            raise click.ClickException(
                "ESPHome not found. Please install ESPHome or uv:\n"
                "  pip install esphome\n"
                "Or use --skip-compile with --firmware to provide a pre-built binary."
            )

    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        raise click.ClickException(
            f"ESPHome compilation failed with exit code {result.returncode}"
        )


def find_firmware(yaml_file: Path, project_name: str) -> Path | None:
    """Try to find the firmware binary for the given YAML file."""
    yaml_dir = yaml_file.parent

    # Try same name with .bin extension
    bin_file = yaml_dir / f"{yaml_file.stem}.bin"
    if bin_file.exists():
        return bin_file

    # Try ESPHome build directory
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


def convert_to_esphome_github_url(url: str) -> str | None:
    """Convert a GitHub URL to ESPHome's github:// format for dashboard_import.

    GitHub URL: https://github.com/user/repo/blob/branch/path/file.yaml
    ESPHome format: github://user/repo/path/file.yaml@branch
    """
    github_blob = re.match(
        r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)", url
    )
    if github_blob:
        user, repo, branch, path = github_blob.groups()
        return f"github://{user}/{repo}/{path}@{branch}"
    return None


def create_factory_yaml(
    yaml_file: Path,
    publish_url: str,
    package_import_url: str | None,
    version: str | None,
) -> Path:
    """Create a factory YAML that imports the original and adds OTA support.

    Creates a .factory.yaml file that:
    - Imports the original YAML as a package
    - Adds OTA, update, http_request components (only if version is provided)
    - Optionally adds dashboard_import

    Returns the path to the factory YAML file.
    """
    # Build the factory YAML content
    factory_content = """# Factory firmware - generated by ewt-gen
# Users should import {original_filename} directly, not this file.

packages:
  original: !include {original_filename}
""".format(original_filename=yaml_file.name)

    # Only include OTA components if version is provided
    if version:
        publish_url = publish_url.rstrip("/")
        manifest_url = f"{publish_url}/manifest.json"
        factory_content += """
esphome:
  project:
    version: "{version}"

ota:
  - platform: http_request
    id: ota_http_request

update:
  - platform: http_request
    id: update_http_request
    name: Firmware
    source: {manifest_url}

http_request:
""".format(version=version, manifest_url=manifest_url)

    if package_import_url:
        factory_content += """
dashboard_import:
  package_import_url: {package_import_url}
""".format(package_import_url=package_import_url)

    # Create factory YAML file in the same directory
    factory_file = yaml_file.parent / f"{yaml_file.stem}.factory.yaml"
    factory_file.write_text(factory_content.lstrip())

    return factory_file


if __name__ == "__main__":
    main()
