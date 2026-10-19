#!/usr/bin/env python3
"""MCP benchmark tools for the bundled public discount fixture ONLY.

Not a production project runner or general filesystem/shell interface. This
capability-limited alternative can test real CLI/model tool calls when a nested
OS sandbox is unavailable. No caller-supplied paths or commands are accepted.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical_ast(source):
    tree = ast.parse(source) if isinstance(source, str) else source
    # Documentation changes have no execution effect. The remaining complete
    # module still has to match the bundled safe arithmetic AST exactly.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                del body[0]
    return ast.dump(tree, include_attributes=False)


class FixtureTools:
    def __init__(self, workspace, audit=None):
        self.workspace = Path(workspace).resolve(strict=True)
        self.audit = Path(audit) if audit else None
        baseline = ROOT / 'examples/demo-project'
        self.original = (baseline / 'discount.py').read_text()
        self.test_bytes = (baseline / 'test_discount.py').read_bytes()
        self.original_ast = canonical_ast(self.original)
        expected = ast.parse(self.original)
        operators = [n for n in ast.walk(expected) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add)]
        if len(operators) != 1:
            raise ValueError('unexpected_bundled_fixture')
        operators[0].op = ast.Sub()
        self.expected_ast = canonical_ast(expected)
        self.calls = 0
        self.guard()

    def guard(self):
        for p in self.workspace.iterdir():
            if p.is_symlink() or p.name not in {'discount.py', 'test_discount.py', '__pycache__'}:
                raise ValueError('workspace_is_not_exclusive_public_fixture')
        test = self.workspace / 'test_discount.py'
        source = self.workspace / 'discount.py'
        if not test.is_file() or test.read_bytes() != self.test_bytes or not source.is_file():
            raise ValueError('fixture_or_tests_changed')
        if source.stat().st_size > 8192:
            raise ValueError('fixture_too_large')
        tree = canonical_ast(source.read_text())
        if tree not in {self.original_ast, self.expected_ast}:
            raise ValueError('arbitrary_code_refused')

    def invoke(self, name, arguments):
        self.calls += 1
        if self.calls > 24:
            raise ValueError('tool_call_budget_exceeded')
        if not isinstance(arguments, dict):
            raise ValueError('invalid_arguments')
        self.guard()
        if name == 'read_fixture' and not arguments:
            result = {'discount.py': (self.workspace / 'discount.py').read_text(), 'test_discount.py': self.test_bytes.decode()}
        elif name == 'write_fixture' and set(arguments) == {'source'}:
            source = arguments['source']
            if not isinstance(source, str) or len(source.encode()) > 8192:
                raise ValueError('invalid_source')
            tree = canonical_ast(source)
            if tree != self.expected_ast:
                raise ValueError('only_intended_arithmetic_patch_allowed: preserve the original function, arguments and imports; change only the discount operator')
            fd, temporary = tempfile.mkstemp(prefix='.write-', dir=self.workspace)
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(source)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary, self.workspace / 'discount.py')
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            result = {'written': True, 'sha256': digest(source.encode())}
        elif name == 'test_fixture' and not arguments:
            # No project-controlled imports or commands: only the exact bundled
            # tests and either the original or arithmetic-only patched module.
            with tempfile.TemporaryDirectory(prefix='codexglasses-fixture-pycache-') as cache:
                # A same-size patch within one timestamp tick must not reuse the
                # original module's bytecode. Neither read nor write project caches.
                run = subprocess.run([sys.executable, '-I', '-B', '-X', 'pycache_prefix=' + cache, '-m', 'unittest', 'discover', '-s', str(self.workspace), '-v'],
                                     cwd=self.workspace, env={'PATH': os.defpath, 'LANG': 'C.UTF-8', 'PYTHONUTF8': '1'},
                                     capture_output=True, text=True, timeout=15)
            result = {'exit_code': run.returncode, 'output': (run.stdout + run.stderr)[-8192:]}
        else:
            raise ValueError('unknown_tool_or_arguments')
        if self.audit:
            with self.audit.open('a') as f:
                f.write(json.dumps({'tool': name, 'source_sha256': digest((self.workspace / 'discount.py').read_bytes()),
                                    'exit_code': result.get('exit_code'), 'written': result.get('written')}) + '\n')
        return result


def serve(tools):
    empty = {'type': 'object', 'properties': {}, 'additionalProperties': False}
    definitions = [
        {'name': 'read_fixture', 'description': 'Read the public discount source and its immutable tests.', 'inputSchema': empty},
        {'name': 'write_fixture', 'description': 'Write the complete corrected discount.py source. Only the intended arithmetic operator patch is allowed; tests and paths cannot change.',
         'inputSchema': {'type': 'object', 'properties': {'source': {'type': 'string'}}, 'required': ['source'], 'additionalProperties': False}},
        {'name': 'test_fixture', 'description': 'Run the fixed public acceptance tests and return the real process exit code.', 'inputSchema': empty}]
    while True:
        line = sys.stdin.buffer.readline(32769)
        if not line:
            return
        if len(line) > 32768:
            return
        request = json.loads(line)
        if 'id' not in request:
            continue
        method = request.get('method')
        response = {'jsonrpc': '2.0', 'id': request['id']}
        if method == 'initialize':
            version = request.get('params', {}).get('protocolVersion', '2024-11-05')
            response['result'] = {'protocolVersion': version, 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'codexglasses-public-fixture', 'version': '0.2.0'}}
        elif method == 'tools/list':
            response['result'] = {'tools': definitions}
        elif method == 'tools/call':
            try:
                parameters = request.get('params', {})
                result = tools.invoke(parameters.get('name'), parameters.get('arguments', {}))
                response['result'] = {'content': [{'type': 'text', 'text': json.dumps(result)}], 'isError': False}
            except (ValueError, SyntaxError, OSError, subprocess.TimeoutExpired) as e:
                response['result'] = {'content': [{'type': 'text', 'text': type(e).__name__ + ': ' + str(e)[:200]}], 'isError': True}
                if tools.audit:
                    with tools.audit.open('a') as f:
                        f.write(json.dumps({'tool': request.get('params', {}).get('name'), 'rejected': True, 'reason': type(e).__name__ + ': ' + str(e)[:200]}) + '\n')
        elif method == 'ping':
            response['result'] = {}
        else:
            response['error'] = {'code': -32601, 'message': 'unsupported_method'}
        sys.stdout.write(json.dumps(response) + '\n')
        sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture-directory', required=True, type=Path)
    parser.add_argument('--audit', type=Path)
    args = parser.parse_args()
    serve(FixtureTools(args.fixture_directory, args.audit))


if __name__ == '__main__':
    main()
