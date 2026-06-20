import hashlib

def _sync_projects_to_db():
    """Sync projects.yaml → SQLite, but only if YAML content changed."""
    yaml_path = settings.projects_yaml
    if not yaml_path.exists():
        return

    content = yaml_path.read_bytes()
    content_hash = hashlib.md5(content).hexdigest()
    hash_file = yaml_path.parent / ".projects_yaml.hash"

    if hash_file.exists() and hash_file.read_text().strip() == content_hash:
        print("[filesystem-server] projects.yaml unchanged, skipping sync")
        return

    for p in _load_yaml_projects():
        mem.upsert_project(
            id=p["id"], name=p["name"], path=p["path"],
            description=p.get("description"), github_repo=p.get("github_repo"),
            tags=p.get("tags", []),
        )
    hash_file.write_text(content_hash)
    print("[filesystem-server] synced projects.yaml to database")