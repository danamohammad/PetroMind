"""Prepare the bounded Cloudflare package bundle; never execute a scientific model.

First install the locked Pyodide packages with pywrangler sync. Then run this file,
and deploy using Wrangler directly (so a new sync cannot replace the adaptations).
"""
from pathlib import Path
import argparse
import ast
import shutil

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--packages', type=Path, help='Original Pyodide site-packages directory')
args = parser.parse_args()
sources = list((ROOT / '.venv-workers/pyodide-venv/lib').glob('python*/site-packages'))
source = args.packages or (sources[0] if len(sources) == 1 else None)
if source is None or not list((source / 'numpy').rglob('*wasm32*.so')):
    raise SystemExit('Supply the original Pyodide site-packages; native macOS/Linux wheels are not compatible.')
vendor = ROOT / 'python_modules'
if vendor.exists(): shutil.rmtree(vendor)
shutil.copytree(source, vendor)

def without_documentation(path):
    raw = path.read_text()
    try: tree = ast.parse(raw)
    except SyntaxError: return
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    prefix = []
    for line in raw.splitlines():
        if line.startswith('#') or not line.strip(): prefix.append(line)
        else: break
    path.write_text('\n'.join(prefix) + '\n' + ast.unparse(tree) + '\n')

# NumPy uses some docstrings when constructing masked-array functions: preserve it intact.
# All distribution license files are retained. Scientific function bodies are unchanged.
for package in ('chemicals', 'thermo', 'fluids', 'scipy'):
    for path in (vendor / package).rglob('*.py'): without_documentation(path)

def public_symbols(path):
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__all__' for t in node.targets):
            try: return ast.literal_eval(node.value)
            except (ValueError, TypeError): pass
    return []

def lazy_initializer(package, symbols, modules, extra=''):
    code = '# PetroMind deployment adapter: defer unused imports; numerical modules are unchanged.\nimport importlib\n'
    code += extra + '\nSYMBOLS = ' + repr(symbols) + '\nMODULES = ' + repr(modules)
    code += '''
__all__ = list(SYMBOLS) + MODULES
def __getattr__(name):
    if name in SYMBOLS:
        module, symbol = SYMBOLS[name]
        value = getattr(importlib.import_module('.'+module, __name__), symbol)
    elif name in MODULES:
        value = importlib.import_module('.'+name, __name__)
    else:
        raise AttributeError(name)
    globals()[name] = value
    return value
'''
    (package / '__init__.py').write_text(code)

package = vendor / 'fluids'
symbols, modules = {}, []
for path in package.glob('*.py'):
    if path.name.startswith('_'): continue
    modules.append(path.stem)
    symbols.update({name: (path.stem, name) for name in public_symbols(path)})
lazy_initializer(package, symbols, modules, "from . import constants, numerics\n__version__ = '1.3.1'")

package = vendor / 'scipy/optimize'
symbols, modules = {}, []
for node in ast.parse((package / '__init__.py').read_text()).body:
    if not isinstance(node, ast.ImportFrom) or node.level != 1: continue
    if node.module is None:
        modules.extend(alias.name for alias in node.names)
        continue
    for alias in node.names:
        if alias.name != '*': symbols[alias.asname or alias.name] = (node.module, alias.name)
        else:
            path = package / (node.module + '.py')
            if path.exists(): symbols.update({name: (node.module, name) for name in public_symbols(path)})
lazy_initializer(package, symbols, modules)

public = ROOT.parent / 'public'
for name in ('Fluid Engine.py', 'Physical Models.py', 'Engineering Models.py'):
    shutil.copyfile(public / name, ROOT / 'Source' / name)
engine = ast.parse((public / 'Fluid Engine.py').read_text())
reader = next(node for node in engine.body if isinstance(node, ast.FunctionDef) and node.name == 'read_file')
(ROOT / 'Source/Import Reader.py').write_text('import base64, csv, io\n' + ast.unparse(reader) + '\n')
print('Prepared scientific source and deployment-only package adaptations. No calculations executed.')
