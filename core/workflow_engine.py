"""
AuraOS · Workflow Engine
========================
Loads YAML workflow definitions and executes them.
Variables are resolved against a context dict before execution.
"""
import re
import yaml
from pathlib import Path
from collections.abc import Generator
from typing import Any

WORKFLOWS_DIR = Path(__file__).parent.parent / "workflows"


def load_workflow(workflow_id: str) -> dict:
    """Load a workflow definition by id."""
    path = WORKFLOWS_DIR / f"{workflow_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Workflow '{workflow_id}' not found at {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def list_workflows() -> list[dict]:
    """List all available workflows."""
    workflows = []
    for path in WORKFLOWS_DIR.glob("*.yaml"):
        with open(path) as f:
            w = yaml.safe_load(f)
            workflows.append({
                "id":          w.get("id"),
                "name":        w.get("name"),
                "description": w.get("description"),
                "triggers":    w.get("triggers", []),
            })
    return workflows


def match_workflow(user_input: str) -> dict | None:
    """
    Find a workflow whose triggers match the user input.
    Returns the workflow dict or None.
    """
    user_lower = user_input.lower()
    for workflow in list_workflows():
        for trigger in workflow.get("triggers", []):
            if trigger.lower() in user_lower:
                return load_workflow(workflow["id"])
    return None


def resolve_variables(value: Any, context: dict) -> Any:
    """
    Replace {variable} placeholders in strings with context values.
    Works recursively on dicts and lists.
    """
    if isinstance(value, str):
        def replace(match):
            key = match.group(1)
            return str(context.get(key, match.group(0)))
        return re.sub(r"\{(\w+)\}", replace, value)
    elif isinstance(value, dict):
        return {k: resolve_variables(v, context) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_variables(item, context) for item in value]
    return value


def build_workflow_context(
    workflow: dict,
    user_input: str,
    agent_context: dict = None,
) -> dict:
    """
    Build the variable context for a workflow run.
    Merges: defaults → agent context → extracted values.
    """
    ctx = {}

    # Load defaults from workflow variables
    for var in workflow.get("variables", []):
        if var.get("default") is not None:
            ctx[var["name"]] = var["default"]

    # Merge agent context (project paths, ids, etc.)
    if agent_context:
        ctx.update(agent_context)

    return ctx


class WorkflowExecutor:
    """
    Executes a workflow definition, yielding streaming tokens.

    Usage:
        executor = WorkflowExecutor(workflow, context, tool_executor)
        for token in executor.run():
            print(token, end="", flush=True)
    """

    def __init__(self, workflow: dict, context: dict, tool_executor):
        self.workflow = workflow
        self.context  = context
        self.executor = tool_executor  # core.executor.Executor instance

    def run(self) -> Generator[str, None, None]:
        name  = self.workflow.get("name", "Workflow")
        steps = self.workflow.get("steps", [])

        yield f"\n⚡ Running workflow: {name}\n"
        yield f"   {len(steps)} steps\n\n"

        for i, step in enumerate(steps):
            step_name = step.get("name", f"Step {i+1}")
            tool_name = step.get("tool", "")
            raw_params = step.get("params", {})
            needs_confirm = step.get("requires_confirmation", False)
            skip_if_missing = step.get("skip_if_missing", [])

            # Skip step if required context vars are missing/empty
            missing = [v for v in skip_if_missing if not self.context.get(v)]
            if missing:
                yield f"  [{i+1}/{len(steps)}] {step_name} — ⏭ skipped (missing: {', '.join(missing)})\n"
                continue

            params = resolve_variables(raw_params, self.context)
            yield f"  [{i+1}/{len(steps)}] {step_name}\n"

            if needs_confirm:
                yield f"  ⚠️  Requires confirmation — proceeding automatically in CLI mode\n"

            result = self.executor._execute_tool(tool_name, params)

            if result and result.success:
                yield f"  ✓ {result.message or step_name} \n"
                if result.output and isinstance(result.output, dict):
                    self.context.update(result.output)
            else:
                error = result.error if result else "unknown error"
                yield f"  ✗ Failed: {error}\n"
                if step.get("abort_on_failure", True):
                    yield f"\n❌ Workflow aborted at step {i+1}.\n"
                    return

        yield f"\n✅ Workflow complete: {name}\n"