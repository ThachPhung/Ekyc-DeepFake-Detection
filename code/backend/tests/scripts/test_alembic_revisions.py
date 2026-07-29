import ast
from pathlib import Path

VERSIONS_DIR = (
    Path(__file__).resolve().parents[2] / "app" / "alembic" / "versions"
)


def _literal_assignment(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"Missing {name!r} assignment")


def _revision_graph() -> dict[str, tuple[str | tuple[str, ...] | None, Path]]:
    graph = {}
    for path in VERSIONS_DIR.glob("*.py"):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        revision = _literal_assignment(module, "revision")
        down_revision = _literal_assignment(module, "down_revision")
        graph[revision] = (down_revision, path)
    return graph


def test_alembic_revisions_have_single_head() -> None:
    graph = _revision_graph()
    parent_revisions = {
        parent
        for down_revision, _ in graph.values()
        for parent in (
            down_revision if isinstance(down_revision, tuple) else (down_revision,)
        )
        if parent is not None
    }

    heads = sorted(set(graph) - parent_revisions)

    assert heads == ["identity20260706"]


def test_alembic_down_revisions_exist() -> None:
    graph = _revision_graph()
    missing = {}

    for revision, (down_revision, path) in graph.items():
        parents = down_revision if isinstance(down_revision, tuple) else (down_revision,)
        missing_parents = [parent for parent in parents if parent and parent not in graph]
        if missing_parents:
            missing[revision] = {
                "file": path.name,
                "missing_parents": missing_parents,
            }

    assert missing == {}
