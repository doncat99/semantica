"""Host-controlled service lifetime; graph semantics remain in NativeScope."""
import asyncio
import hmac
import json
import os
import threading

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .markdown_resources import MarkdownResourceRegistry
from .native_scope import MAX_BYTES, install_native_scope


class NativeService:
    def __init__(self, app):
        self.app = app
        self.control_key = os.environ.get('SEMANTICA_EXPLORER_CONTROL_KEY')
        if not self.control_key:
            raise ValueError('Native Explorer service requires a host control key')
        self.scope = None
        self.api_key = None
        self.origin = None
        self.bound = False
        self.cancelled = threading.Event()
        self.requests = set()
        self.lock = asyncio.Lock()

    def authorize_control(self, request):
        candidate = request.headers.get('x-explorer-control-key', '')
        if not hmac.compare_digest(candidate.encode(), self.control_key.encode()):
            raise HTTPException(401, 'Invalid host control key')
        # A browser may never use the host-only management channel.
        if request.headers.get('origin') is not None:
            raise HTTPException(403, 'Host control channel does not accept browser requests')

    def get_scope(self):
        if not self.bound or self.scope is None:
            raise HTTPException(503, 'No Project session is bound')
        return self.scope

    async def unbind(self):
        self.cancelled.set()
        self.bound = False
        self.api_key = None
        self.origin = None
        if self.scope:
            self.scope._cancelled.set()
        await self.app.state.ws_manager.close_all()
        # Drain admitted requests before swapping the shared native GraphSession.
        if self.requests:
            pending = set(self.requests)
            _done, pending = await asyncio.wait(pending, timeout=5)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        if self.scope:
            await run_in_threadpool(self.scope.close)
            self.scope = None
        self.app.state.session = None
        self.app.state.markdown_resources = None


def install_native_service(app):
    service = NativeService(app)
    app.state.native_service = service
    install_native_scope(app, service.get_scope)

    @app.middleware('http')
    async def fence_project(request: Request, call_next):
        path = request.url.path
        if (not path.startswith('/api/') or path in {'/api/health', '/api/info'}
                or path.startswith('/api/native-service/')):
            return await call_next(request)
        if request.method == 'OPTIONS':
            return await call_next(request)
        if not service.bound:
            return JSONResponse(status_code=503, content={'detail': 'No Project session is bound'})
        origin = request.headers.get('origin')
        if origin is not None and origin != service.origin:
            return JSONResponse(status_code=403, content={'detail': 'Project session origin does not match'})
        if not hmac.compare_digest(request.headers.get('x-api-key', '').encode(), service.api_key.encode()):
            return JSONResponse(status_code=401, content={'detail': 'Invalid Project session key'})
        task = asyncio.current_task()
        service.requests.add(task)
        try:
            return await call_next(request)
        finally:
            service.requests.discard(task)

    @app.post('/api/native-service/cancel')
    async def cancel(request: Request):
        service.authorize_control(request)
        service.cancelled.set()
        if service.scope:
            service.scope._cancelled.set()
        return {'state': 'cancellation_requested'}

    @app.delete('/api/native-service/session')
    async def unbind(request: Request):
        service.authorize_control(request)
        async with service.lock:
            await service.unbind()
        return {'state': 'unbound'}

    @app.post('/api/native-service/session')
    async def bind(request: Request):
        service.authorize_control(request)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise HTTPException(413, 'Native session request exceeds byte budget')
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise HTTPException(422, 'Invalid native session request') from error
        fields = {'path', 'projectId', 'generation', 'apiKey', 'origin'}
        if (not isinstance(data, dict) or set(data) != fields
                or not all(isinstance(data[key], str) and 0 < len(data[key]) <= 4096 for key in fields)):
            raise HTTPException(422, 'Native session requires exact path, Project, generation, key and origin')
        if not data['apiKey'].isascii():
            raise HTTPException(422, 'Native session key must be ASCII')
        from urllib.parse import urlsplit
        origin = urlsplit(data['origin'])
        if data['origin'] != 'ontoscience://app' and not (
            origin.scheme in {'http', 'https'} and origin.hostname in {'localhost', '127.0.0.1', '::1'}
            and origin.netloc and not origin.path and not origin.query and not origin.fragment
            and origin.username is None and origin.password is None
        ):
            raise HTTPException(422, 'Native session requires a loopback App origin')
        async with service.lock:
            await service.unbind()
            service.cancelled.clear()
            try:
                from .native_scope import NativeScope
                service.scope = await run_in_threadpool(NativeScope, data['path'], data['projectId'], data['generation'])
                session, _ = await run_in_threadpool(service.scope.select, {}, cancel_event=service.cancelled)
                service.app.state.session = session
                service.app.state.markdown_resources = MarkdownResourceRegistry(session.graph, service.app.state.agent_memory)
                service.api_key, service.origin = data['apiKey'], data['origin']
                service.app.state.explorer_settings['allowed_origins'][:] = [data['origin']]
                service.bound = True
            except (ValueError, TimeoutError) as error:
                await service.unbind()
                raise HTTPException(422, str(error)) from error
            except BaseException:
                await service.unbind()
                raise
        return {'state': 'bound', 'projectId': data['projectId'], 'generation': data['generation']}
