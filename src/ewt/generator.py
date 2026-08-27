"""Static site generator for ESP Web Tools."""

import hashlib
import html
import json
import os
import re
import shutil
import zipfile
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path


def _file_hashes(path: Path) -> tuple[str, str]:
    """Return the (md5, sha256) hex digests of a file."""
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


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
        - config_includes: Local files the YAML pulls in via !include
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

        # Copy firmware with chip-specific name (including version if available)
        chip_id = chip_family.lower().replace('-', '')
        if version:
            firmware_filename = f"firmware-{chip_id}-{version}.bin"
        else:
            firmware_filename = f"firmware-{chip_id}.bin"
        firmware_dest = output_dir / firmware_filename
        shutil.copy(firmware_file, firmware_dest)

        manifest_build = {
            "chipFamily": chip_family,
            "parts": [{"path": firmware_filename, "offset": 0}],
        }

        # Add the OTA (app-only) image so ESPHome's update.http_request platform
        # can perform over-the-air updates from this manifest.
        ota_firmware_file = build.get("ota_firmware")
        if ota_firmware_file:
            if version:
                ota_filename = f"firmware-{chip_id}-{version}.ota.bin"
            else:
                ota_filename = f"firmware-{chip_id}.ota.bin"
            shutil.copy(ota_firmware_file, output_dir / ota_filename)

            md5, sha256 = _file_hashes(ota_firmware_file)
            ota_entry = {
                "path": ota_filename,
                "md5": md5,
                "sha256": sha256,
            }
            if build.get("release_summary"):
                ota_entry["summary"] = build["release_summary"]
            if build.get("release_url"):
                ota_entry["release_url"] = build["release_url"]
            manifest_build["ota"] = ota_entry

        manifest_builds.append(manifest_build)

        # Copy YAML files (avoid duplicates)
        if yaml_file.name not in yaml_files_copied:
            shutil.copy(yaml_file, output_dir / yaml_file.name)
            yaml_files_copied.add(yaml_file.name)

        if include_original_yaml and compile_yaml_file.name not in yaml_files_copied:
            shutil.copy(compile_yaml_file, output_dir / compile_yaml_file.name)
            yaml_files_copied.add(compile_yaml_file.name)

        # A config built from local packages is incomplete on its own, so ship
        # the whole tree as a zip and link that instead of the entry file.
        config_zip_filename = None
        includes = build.get("config_includes") or []
        if includes:
            config_zip_filename = f"{yaml_file.stem}-config.zip"
            write_config_zip(
                output_dir / config_zip_filename, yaml_file, includes
            )

        # Collect tab data
        tab_data.append({
            "chip_family": chip_family,
            "chip_id": chip_id,
            "firmware_filename": firmware_filename,
            "yaml_filename": yaml_file.name,
            "config_zip_filename": config_zip_filename,
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
    if version and version != "dev":
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


def write_config_zip(zip_path: Path, yaml_file: Path, includes: list[Path]) -> None:
    """Bundle a config and its local includes into one zip.

    Paths are stored relative to the deepest directory holding all of them, so
    the !include references inside the files keep resolving once unpacked.
    """
    files = [yaml_file, *includes]
    root = Path(os.path.commonpath([str(f.parent) for f in files]))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, file.relative_to(root))


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

        # With local packages the entry file alone is not usable, so point the
        # download at the zip holding the whole config tree.
        if tab["config_zip_filename"]:
            config_link = (
                f'<a href="{tab["config_zip_filename"]}" download '
                f'class="download-link">Download ZIP</a>'
            )
        else:
            config_link = (
                f'<a href="{tab["yaml_filename"]}" download '
                f'class="download-link">Download</a>'
            )

        # Content
        content_parts = [
            f'<div class="tab-content content-{chip_id}">',
            f'  <div class="firmware-row"><span>Firmware</span> <a href="{tab["firmware_filename"]}" download class="download-link">Download</a></div>',
            f'  <details class="yaml-details">',
            f'    <summary><span class="summary-content">Configuration {config_link}</span></summary>',
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
