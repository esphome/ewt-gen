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
    builds: list[dict],
    title: str,
    version: str | None = None,
    include_original_yaml: bool = False,
):
    """Generate a static website for firmware distribution.

    builds is a list of dicts with keys:
        - yaml_file: Path to original YAML
        - compile_yaml_file: Path to compiled YAML (may include factory additions)
        - firmware: Path to firmware binary
        - chip_family: Normalized chip family string
    """
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy files for each build and collect tab data
    manifest_builds = []
    yaml_files_copied = set()
    tab_data = []

    for build in builds:
        yaml_file = build["yaml_file"]
        compile_yaml_file = build["compile_yaml_file"]
        firmware_file = build["firmware"]
        chip_family = build["chip_family"]

        # Copy firmware with chip-specific name
        firmware_filename = f"firmware-{chip_family.lower().replace('-', '')}.bin"
        firmware_dest = output_dir / firmware_filename
        shutil.copy(firmware_file, firmware_dest)

        manifest_builds.append({
            "chipFamily": chip_family,
            "parts": [{"path": firmware_filename, "offset": 0}],
        })

        # Copy YAML files (avoid duplicates)
        if yaml_file.name not in yaml_files_copied:
            shutil.copy(yaml_file, output_dir / yaml_file.name)
            yaml_files_copied.add(yaml_file.name)

        if include_original_yaml and compile_yaml_file.name not in yaml_files_copied:
            shutil.copy(compile_yaml_file, output_dir / compile_yaml_file.name)
            yaml_files_copied.add(compile_yaml_file.name)

        # Collect tab data
        tab_data.append({
            "chip_family": chip_family,
            "chip_id": chip_family.lower().replace("-", ""),
            "firmware_filename": firmware_filename,
            "yaml_filename": yaml_file.name,
            "yaml_content": html.escape(yaml_file.read_text()),
            "compile_yaml_filename": compile_yaml_file.name if include_original_yaml else None,
            "compile_yaml_content": html.escape(compile_yaml_file.read_text()) if include_original_yaml else None,
        })

    # Generate manifest.json
    manifest = generate_manifest(
        name=title,
        builds=manifest_builds,
        version=version,
    )
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Generate index.html from template
    build_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Build tab HTML
    tab_css, tab_inputs, tab_labels, tab_contents = generate_tabs_html(
        tab_data, include_original_yaml
    )

    # Build version badge HTML
    version_badge = ""
    if version:
        version_badge = f' <span class="version-badge">v{version}</span>'

    html_output = render_template(
        "index.html",
        title=title,
        version_badge=version_badge,
        build_date=build_date,
        tab_css=tab_css,
        tab_inputs=tab_inputs,
        tab_labels=tab_labels,
        tab_contents=tab_contents,
    )
    html_path = output_dir / "index.html"
    with open(html_path, "w") as f:
        f.write(html_output)


def generate_tabs_html(tab_data: list[dict], include_original_yaml: bool) -> tuple[str, str, str, str]:
    """Generate HTML for chip selection tabs.

    Returns (tab_css, tab_inputs, tab_labels, tab_contents).
    """
    tab_css_parts = []
    tab_inputs_parts = []
    tab_labels_parts = []
    tab_contents_parts = []

    for i, tab in enumerate(tab_data):
        chip_id = tab["chip_id"]
        chip_family = tab["chip_family"]
        checked = " checked" if i == 0 else ""

        # CSS for this tab (show content when radio is checked, style active label)
        tab_css_parts.append(
            f"#tab-{chip_id}:checked ~ .tab-content.content-{chip_id} {{ display: block; }}\n"
            f"#tab-{chip_id}:checked ~ .tab-labels label[for='tab-{chip_id}'] {{ "
            f"background: var(--card-bg); border-color: var(--border-color); }}"
        )

        # Radio input
        tab_inputs_parts.append(
            f'<input type="radio" name="chip-tab" id="tab-{chip_id}"{checked}>'
        )

        # Label
        tab_labels_parts.append(f'<label for="tab-{chip_id}">{chip_family}</label>')

        # Content
        content_parts = [
            f'<div class="tab-content content-{chip_id}">',
            f'  <div class="firmware-row"><span>Firmware</span> <a href="{tab["firmware_filename"]}" download class="download-link">Download</a></div>',
            f'  <details class="yaml-details">',
            f'    <summary><span class="summary-content">Configuration <a href="{tab["yaml_filename"]}" download class="download-link">Download</a></span></summary>',
            f'    <pre><code>{tab["yaml_content"]}</code></pre>',
            f'  </details>',
        ]

        # Add OTA extension accordion if available
        if include_original_yaml and tab["compile_yaml_filename"]:
            content_parts.extend([
                f'  <details class="yaml-details">',
                f'    <summary><span class="summary-content">OTA extension <a href="{tab["compile_yaml_filename"]}" download class="download-link">Download</a></span></summary>',
                f'    <pre><code>{tab["compile_yaml_content"]}</code></pre>',
                f'  </details>',
            ])

        content_parts.append('</div>')
        tab_contents_parts.append('\n'.join(content_parts))

    return (
        "\n    ".join(tab_css_parts),
        "\n    ".join(tab_inputs_parts),
        "\n      ".join(tab_labels_parts),
        "\n    ".join(tab_contents_parts),
    )


def generate_manifest(name: str, builds: list[dict], version: str | None = None) -> dict:
    """Generate the ESP Web Tools manifest.

    builds is a list of dicts with keys:
        - chipFamily: The chip family string
        - parts: List of firmware parts with path and offset
    """
    manifest = {
        "name": name,
        "builds": builds,
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
