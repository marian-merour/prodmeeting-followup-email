"""Jinja2 template loading and rendering."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


class TemplateLoader:
    """Load and render email templates."""

    def __init__(self, templates_dir: Path):
        """
        Initialize template loader.

        Args:
            templates_dir: Directory containing template files
        """
        self.templates_dir = templates_dir
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, **context: Any) -> str:
        """
        Render a template with context variables.

        Args:
            template_name: Name of template file
            **context: Template variables

        Returns:
            Rendered template string
        """
        template = self.env.get_template(template_name)
        return template.render(**context)
