"""Static site generator for ESP Web Tools."""

import html
import json
import re
import shutil
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path


def generate_site(
    output_dir: Path,
    yaml_file: Path,
    firmware_file: Path,
    chip_family: str,
    title: str,
    original_yaml_file: Path | None = None,
    version: str | None = None,
):
    """Generate a static website for firmware distribution."""
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy files
    yaml_dest = output_dir / yaml_file.name
    firmware_dest = output_dir / "firmware.bin"

    shutil.copy(yaml_file, yaml_dest)
    shutil.copy(firmware_file, firmware_dest)

    # Copy original YAML if provided (for factory builds that use !include)
    if original_yaml_file is not None:
        original_dest = output_dir / original_yaml_file.name
        shutil.copy(original_yaml_file, original_dest)

    # Generate manifest.json
    manifest = generate_manifest(
        name=title,
        chip_family=chip_family,
        version=version,
    )
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Generate index.html from template
    build_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Build ESPHome configuration section based on whether we have factory + original
    if original_yaml_file is not None:
        esphome_config_html = (
            f'Download <a href="{original_yaml_file.name}" download>original configuration</a> '
            f'and the <a href="{yaml_file.name}" download>OTA/import extension</a> '
            f'to customize it with <a href="https://esphome.io" target="_blank">ESPHome</a>.'
        )
        # Read original YAML content for display
        yaml_content = original_yaml_file.read_text()
    else:
        esphome_config_html = (
            f'Download the <a href="{yaml_file.name}" download>YAML configuration</a> '
            f'to customize it with <a href="https://esphome.io" target="_blank">ESPHome</a>.'
        )
        # Read YAML content for display
        yaml_content = yaml_file.read_text()

    # HTML-escape the YAML content to prevent XSS
    yaml_content_escaped = html.escape(yaml_content)

    html_output = render_template(
        "index.html",
        title=title,
        yaml_filename=yaml_file.name,
        chip_family=chip_family,
        build_date=build_date,
        esphome_config_html=esphome_config_html,
        yaml_content=yaml_content_escaped,
    )
    html_path = output_dir / "index.html"
    with open(html_path, "w") as f:
        f.write(html_output)


def generate_manifest(name: str, chip_family: str, version: str | None = None) -> dict:
    """Generate the ESP Web Tools manifest."""
    manifest = {
        "name": name,
        "builds": [
            {
                "chipFamily": chip_family,
                "parts": [{"path": "firmware.bin", "offset": 0}],
            }
        ],
    }

    # Add version and home_assistant_domain if version is provided
    if version:
        manifest["version"] = version
        manifest["home_assistant_domain"] = "esphome"

    return manifest


def render_template(template_name: str, **context) -> str:
    """Render a template with the given context using simple string substitution."""
    template_content = resources.files("ewt.templates").joinpath(template_name).read_text()

    # Simple template rendering: replace {{ variable }} with values
    def replace_var(match):
        var_name = match.group(1).strip()
        return str(context.get(var_name, match.group(0)))

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_var, template_content)
