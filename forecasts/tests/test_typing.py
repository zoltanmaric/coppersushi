"""Guard the whole forecast tree against omitted function annotations."""
import ast
from pathlib import Path
import unittest


class AnnotationTests(unittest.TestCase):
    def test_all_function_signatures_are_annotated(self) -> None:
        missing = []
        root = Path(__file__).resolve().parents[1]
        for path in root.rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                arguments.extend(arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None)
                for arg in arguments:
                    if arg.annotation is None and arg.arg not in ('self', 'cls'):
                        missing.append(f'{path.relative_to(root)}:{node.lineno} {node.name}.{arg.arg}')
                if node.returns is None:
                    missing.append(f'{path.relative_to(root)}:{node.lineno} {node.name} return')
        self.assertEqual(missing, [], '\n'.join(missing))
