"""
AuraOS · Scaffold Tools
=======================
Create local directories and scaffold starter project files.
"""
from pathlib import Path
from tools.base import AuraTool, ToolResult


SCAFFOLDS = {
    "python": {
        "files": {
            "README.md": "# {name}\n\n{description}\n",
            ".gitignore": "__pycache__/\n*.pyc\n.venv/\n.env\n.DS_Store\n",
            "requirements.txt": "",
            "main.py": '"""Entry point for {name}."""\n\n\ndef main():\n    print("Hello from {name}")\n\n\nif __name__ == "__main__":\n    main()\n',
        }
    },
    "node": {
        "files": {
            "README.md": "# {name}\n\n{description}\n",
            ".gitignore": "node_modules/\n.env\n.DS_Store\ndist/\n",
            "package.json": '{{\n  "name": "{slug}",\n  "version": "0.1.0",\n  "description": "{description}",\n  "main": "index.js"\n}}\n',
            "index.js": 'console.log("Hello from {name}");\n',
        }
    },
    "react": {
        "files": {
            "README.md": "# {name}\n\n{description}\n",
            ".gitignore": "node_modules/\n.env\ndist/\nbuild/\n.DS_Store\n",
            "package.json": '{{\n  "name": "{slug}",\n  "version": "0.1.0",\n  "private": true,\n  "scripts": {{\n    "dev": "vite",\n    "build": "vite build"\n  }}\n}}\n',
        }
    },
}


class CreateDirectory(AuraTool):
    name = "create_directory"
    description = "Create a new local directory for a project."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or ~ path to create"}
        },
        "required": ["path"],
    }
    is_reversible = True
    category = "filesystem"

    def execute(self, path: str) -> ToolResult:
        target = Path(path).expanduser()
        if target.exists():
            return self.ok(message=f"Directory already exists: {target}", output={"path": str(target)})
        try:
            target.mkdir(parents=True, exist_ok=False)
            return self.ok(message=f"Created {target}", output={"path": str(target)})
        except Exception as e:
            return self.fail(error=f"Failed to create directory: {e}")


class ScaffoldProject(AuraTool):
    name = "scaffold_project"
    description = "Generate starter files for a new project (README, .gitignore, entry file)."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "type": {"type": "string", "description": "python | node | react"},
            "name": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["path", "type", "name"],
    }
    is_reversible = True
    category = "filesystem"

    def execute(self, path: str, type: str, name: str, description: str = "") -> ToolResult:
        target = Path(path).expanduser()
        if not target.exists():
            return self.fail(error=f"Directory does not exist: {target}. Run create_directory first.")

        scaffold = SCAFFOLDS.get(type)
        if not scaffold:
            return self.fail(error=f"Unknown project type '{type}'. Supported: {list(SCAFFOLDS.keys())}")

        slug = name.lower().replace(" ", "-")
        created = []
        for filename, content_template in scaffold["files"].items():
            file_path = target / filename
            if file_path.exists():
                continue
            content = content_template.format(name=name, description=description or "", slug=slug)
            file_path.write_text(content)
            created.append(filename)

        return self.ok(
            message=f"Scaffolded {type} project: {len(created)} files created",
            output={"created_files": created, "type": type},
        )
    
import yaml
from config.settings import settings


class RegisterProject(AuraTool):
    name = "register_project"
    description = "Register a new project in AuraOS — adds to projects.yaml for persistence."
    parameters_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "path": {"type": "string"},
            "description": {"type": "string"},
            "github_repo": {"type": "string"},
        },
        "required": ["id", "name", "path"],
    }
    is_reversible = True
    category = "filesystem"

    def execute(
        self, id: str, name: str, path: str,
        description: str = "", github_repo: str = "",
    ) -> ToolResult:
        yaml_path = settings.projects_yaml
        data = {"projects": []}
        if yaml_path.exists():
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {"projects": []}

        # Avoid duplicate entries
        existing_ids = {p["id"] for p in data["projects"]}
        if id in existing_ids:
            return self.ok(message=f"Project '{id}' already registered")

        data["projects"].append({
            "id": id,
            "name": name,
            "path": path,
            "description": description,
            "github_repo": github_repo,
            "tags": [],
        })

        with open(yaml_path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

        return self.ok(
            message=f"Registered project '{id}' in projects.yaml",
            output={"id": id, "path": path},
        )


SCAFFOLD_TOOLS = [CreateDirectory(), ScaffoldProject(), RegisterProject()]
SCAFFOLD_TOOLS_BY_NAME = {t.name: t for t in SCAFFOLD_TOOLS}