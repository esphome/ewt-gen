"""Static site generator for ESP Web Tools."""

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
):
    """Generate a static website for firmware distribution."""
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy files
    yaml_dest = output_dir / yaml_file.name
    firmware_dest = output_dir / "firmware.bin"

    shutil.copy(yaml_file, yaml_dest)
    shutil.copy(firmware_file, firmware_dest)

    # Generate manifest.json
    manifest = generate_manifest(
        name=title,
        chip_family=chip_family,
    )
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Generate index.html from template
    build_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    html = render_template(
        "index.html",
        title=title,
        yaml_filename=yaml_file.name,
        chip_family=chip_family,
        build_date=build_date,
    )
    html_path = output_dir / "index.html"
    with open(html_path, "w") as f:
        f.write(html)


def generate_manifest(name: str, chip_family: str) -> dict:
    """Generate the ESP Web Tools manifest."""
    return {
        "name": name,
        "builds": [
            {
                "chipFamily": chip_family,
                "parts": [{"path": "firmware.bin", "offset": 0}],
            }
        ],
    }


def render_template(template_name: str, **context) -> str:
    """Render a template with the given context using simple string substitution."""
    template_content = resources.files("ewt.templates").joinpath(template_name).read_text()

    # Simple template rendering: replace {{ variable }} with values
    def replace_var(match):
        var_name = match.group(1).strip()
        return str(context.get(var_name, match.group(0)))

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_var, template_content)
