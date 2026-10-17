import ast
from pathlib import Path


def _attribute_parts(node: ast.AST) -> tuple[str, ...] | None:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        parent = _attribute_parts(node.value)
        if parent is None:
            return None
        return (*parent, node.attr)
    return None


def _target_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in node.elts:
            names.extend(_target_names(element))
        return tuple(names)
    return ()


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
    if isinstance(node, ast.Assign):
        return tuple(
            name
            for target in node.targets
            for name in _target_names(target)
        )
    return _target_names(node.target)


def _stream_reference(
    node: ast.AST,
    sys_aliases: set[str],
    stream_names: set[str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in stream_names
    parts = _attribute_parts(node)
    if parts is None or len(parts) < 2:
        return False
    return parts[0] in sys_aliases and parts[1] in {
        "stdout",
        "stderr",
        "__stdout__",
        "__stderr__",
    }


def _is_stream_import(node: ast.ImportFrom) -> bool:
    if node.module in {"io", "_io", "tempfile"}:
        return True
    if node.module == "sys":
        return any(alias.name in {"stdout", "stderr", "__stdout__", "__stderr__"} for alias in node.names)
    if node.module == "os":
        return any(alias.name in {"fdopen", "open"} for alias in node.names)
    return False


def _has_write_mode(call: ast.Call, mode_index: int) -> bool:
    values: list[str] = []
    if len(call.args) > mode_index:
        argument = call.args[mode_index]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            values.append(argument.value)
    for keyword in call.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            if isinstance(keyword.value.value, str):
                values.append(keyword.value.value)
    return any(any(character in value for character in "wax+") for value in values)


def test_only_terminal_output_owns_streams() -> None:
    source_root = Path(__file__).parents[1] / "src"
    violations: list[str] = []

    for path in sorted(source_root.rglob("*.py")):
        relative_path = path.relative_to(source_root).as_posix()
        if relative_path == "terminal_browser/term/output.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        sys_aliases = {"sys"}
        os_aliases = {"os"}
        builtins_aliases = {"builtins"}
        print_aliases = {"print"}
        open_aliases = {"open"}
        os_write_aliases: set[str] = set()
        stream_names: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if alias.name == "sys":
                        sys_aliases.add(name)
                    elif alias.name == "os":
                        os_aliases.add(name)
                    elif alias.name == "builtins":
                        builtins_aliases.add(name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if node.module == "sys" and alias.name in {
                        "stdout",
                        "stderr",
                        "__stdout__",
                        "__stderr__",
                    }:
                        stream_names.add(name)
                    elif node.module == "builtins" and alias.name == "print":
                        print_aliases.add(name)
                    elif node.module == "builtins" and alias.name == "open":
                        open_aliases.add(name)
                    elif node.module == "os" and alias.name == "write":
                        os_write_aliases.add(name)
                if _is_stream_import(node):
                    violations.append(f"{path}:{node.lineno}: imported stream or file object")

        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if value is None:
                    continue
                if _stream_reference(value, sys_aliases, stream_names):
                    stream_names.update(_assigned_names(node))
                if isinstance(value, ast.Name) and value.id == "print":
                    print_aliases.update(_assigned_names(node))
                if isinstance(value, ast.Name) and value.id in open_aliases:
                    open_aliases.update(_assigned_names(node))

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in stream_names:
                violations.append(f"{path}:{node.lineno}: standard stream alias")
            elif isinstance(node, ast.Attribute) and _stream_reference(
                node, sys_aliases, stream_names
            ):
                violations.append(f"{path}:{node.lineno}: standard stream access")
            elif isinstance(node, ast.Call):
                function = node.func
                parts = _attribute_parts(function)
                if isinstance(function, ast.Name) and function.id in print_aliases:
                    violations.append(f"{path}:{node.lineno}: print call")
                elif parts is not None and len(parts) == 2 and parts[0] in builtins_aliases and parts[1] == "print":
                    violations.append(f"{path}:{node.lineno}: print call")
                elif parts is not None and len(parts) == 2 and parts[0] in os_aliases and parts[1] == "write":
                    violations.append(f"{path}:{node.lineno}: os.write call")
                elif isinstance(function, ast.Name) and function.id in os_write_aliases:
                    violations.append(f"{path}:{node.lineno}: os.write call")
                elif parts is not None and parts[0] in stream_names:
                    violations.append(f"{path}:{node.lineno}: standard stream call")
                elif isinstance(function, ast.Name) and function.id in open_aliases and _has_write_mode(node, 1):
                    violations.append(f"{path}:{node.lineno}: file opened for writing")
                elif parts is not None and parts[-1] == "open" and _has_write_mode(node, 0):
                    violations.append(f"{path}:{node.lineno}: file opened for writing")
                elif parts is not None and parts[-1] == "fdopen" and _has_write_mode(node, 1):
                    violations.append(f"{path}:{node.lineno}: file opened for writing")

    assert not violations, "\n".join(violations)
