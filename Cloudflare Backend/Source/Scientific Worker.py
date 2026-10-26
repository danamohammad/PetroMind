"""Private Cloudflare scientific service. Inputs remain in request memory only."""
import json
import gc
import importlib
from datetime import date, datetime
from workers import DurableObject, Response, WorkerEntrypoint

TASKS = {'calculate', 'envelope', 'compare', 'tune', 'import', 'experiments', 'physical', 'engineering'}

def response(value, status=200):
    def encode(value):
        if isinstance(value, (date, datetime)): return value.strftime('%Y-%m-%d')
        raise TypeError('Unsupported result value')
    return Response(json.dumps(value, allow_nan=False, default=encode), status=status,
                    headers={'content-type': 'application/json', 'cache-control': 'no-store'})

def engine_module():
    engine = importlib.import_module('Fluid Engine')
    if not getattr(engine, 'memory_adapter', False):
        original = engine.comparison
        def comparison_with_cleanup(request):
            try:
                return original(request)
            finally:
                gc.collect()
        engine.comparison = comparison_with_cleanup
        engine.progress_callback = lambda message: gc.collect()
        engine.memory_adapter = True
    return engine

def clean(value):
    # Match Fluid Engine.clean without loading the EOS for independent modules.
    import numpy as np
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)): return [clean(v) for v in value]
    if isinstance(value, np.integer): return int(value)
    if isinstance(value, np.bool_): return bool(value)
    if isinstance(value, (float, np.floating)):
        import math
        return float(value) if math.isfinite(value) else None
    return value

class ScientificSolver(DurableObject):
    async def fetch(self, request):
        if request.method != 'POST': return response({'error': 'Method not allowed'}, 405)
        gc.set_threshold(100, 5, 5)
        gc.collect()
        try:
            text = await request.text()
            if len(text.encode()) > 8_000_000: return response({'error': 'Request exceeds 8 MB'}, 413)
            def invalid_constant(value): raise ValueError('Nonfinite JSON is not allowed')
            data = json.loads(text, parse_constant=invalid_constant)
            if not isinstance(data, dict) or data.get('task') not in TASKS:
                return response({'error': 'Unknown calculation request'}, 400)
            task = data['task']
            if task == 'physical':
                result = clean(importlib.import_module('Physical Models').physical_dispatch(data))
            elif task == 'engineering':
                result = clean(importlib.import_module('Engineering Models').engineering_dispatch(data))
            elif task == 'import':
                result = importlib.import_module('Import Reader').read_file(data)
            else:
                result = json.loads(engine_module().dispatch_json(json.dumps(data)))
            return response({'result': result, 'execution': 'Cloudflare Durable Object'})
        except Exception as exc:
            return response({'error': str(exc)[:1200]}, 400)
        finally:
            gc.collect()

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # workers.dev and routes are disabled; only the gateway service binding can call this.
        if request.method != 'POST': return response({'error': 'Method not allowed'}, 405)
        try:
            return await self.env.SOLVER.get(self.env.SOLVER.idFromName('public-science')).fetch(request)
        except Exception:
            return response({'error': 'The free scientific service reached a runtime or memory limit. Reduce the calculation size and retry; no result was produced.'}, 503)
