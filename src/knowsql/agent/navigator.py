"""File system navigation for the schema index."""

from pathlib import Path


class IndexNavigator:
    """Navigates the schema index file hierarchy."""

    def __init__(self, index_dir: str):
        self.root = Path(index_dir).resolve()

    def _is_safe_path(self, resolved: Path) -> bool:
        """Check that resolved path is within the index root."""
        try:
            resolved.relative_to(self.root)
            return True
        except ValueError:
            return False

    def read_file(self, path: str, section: str | None = None) -> str:
        """Read a file from the index, optionally extracting a section."""
        resolved = (self.root / path).resolve()
        if not self._is_safe_path(resolved):
            return "Error: path traversal detected"
        if not resolved.exists():
            return f"Error: file not found: {path}"
        content = resolved.read_text()
        if section:
            return self._extract_section(content, section)
        return content

    def list_directory(self, path: str) -> str:
        """List contents of a directory in the index."""
        resolved = (self.root / path).resolve()
        if not self._is_safe_path(resolved):
            return "Error: path traversal detected"
        if not resolved.exists():
            return f"Error: directory not found: {path}"
        if not resolved.is_dir():
            return f"Error: not a directory: {path}"
        entries = sorted(resolved.iterdir())
        lines = []
        for entry in entries:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")
        return "\n".join(lines) if lines else "(empty directory)"

    def list_all_tables(self) -> list[str]:
        """List all table names in the index."""
        tables = []
        domains_dir = self.root / "domains"
        if domains_dir.exists():
            for domain_dir in sorted(domains_dir.iterdir()):
                tables_dir = domain_dir / "tables"
                if tables_dir.exists():
                    for f in sorted(tables_dir.iterdir()):
                        if f.suffix == ".md" and not f.name.endswith("_columns_detail.md"):
                            tables.append(f.stem)
        return tables

    def list_domains(self) -> list[str]:
        """List all domain names."""
        domains_dir = self.root / "domains"
        if domains_dir.exists():
            return sorted(d.name for d in domains_dir.iterdir() if d.is_dir())
        return []

    def find_and_read_table(self, table_name: str) -> str | None:
        """Find and read a table file by name (handles schema-prefixed filenames)."""
        domains_dir = self.root / "domains"
        if not domains_dir.exists():
            return None
        for domain_dir in sorted(domains_dir.iterdir()):
            tables_dir = domain_dir / "tables"
            if not tables_dir.exists():
                continue
            # Try exact match first
            table_file = tables_dir / f"{table_name}.md"
            if table_file.exists():
                return table_file.read_text()
            # Try schema-prefixed files (pattern: {schema}__{table_name}.md)
            for f in tables_dir.iterdir():
                if f.suffix == ".md" and f.stem.endswith(f"__{table_name}"):
                    return f.read_text()
        return None

    def get_dialect(self) -> str:
        """Get the database dialect from META.json (or fallback to INDEX.md heuristic)."""
        import json
        meta_file = self.root / "META.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                return meta.get("dialect", "sql")
            except (json.JSONDecodeError, OSError):
                pass
        # Fallback: parse INDEX.md
        index_file = self.root / "INDEX.md"
        if index_file.exists():
            content = index_file.read_text()
            for line in content.split("\n"):
                lower = line.lower()
                if "postgresql" in lower or "postgres" in lower:
                    return "postgresql"
                elif "mysql" in lower:
                    return "mysql"
                elif "sqlite" in lower:
                    return "sqlite"
                elif "mssql" in lower or "sql server" in lower:
                    return "mssql"
        return "sql"

    def _extract_section(self, content: str, section: str) -> str:
        """Extract a section from markdown by heading name."""
        lines = content.split("\n")
        in_section = False
        section_lines = []
        section_level = 0

        for line in lines:
            if line.startswith("#"):
                hashes = len(line) - len(line.lstrip("#"))
                heading_text = line.lstrip("#").strip()
                if heading_text.lower() == section.lower():
                    in_section = True
                    section_level = hashes
                    section_lines.append(line)
                    continue
                elif in_section and hashes <= section_level:
                    break
            if in_section:
                section_lines.append(line)

        return "\n".join(section_lines) if section_lines else f"Section '{section}' not found"
