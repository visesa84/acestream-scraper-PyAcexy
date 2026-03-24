"""Main proxy server implementation with CORS, M3U8 and Status list"""
import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from typing import Optional, Dict
from urllib.parse import parse_qs, urlparse, urlunparse, urlencode

# Añadir el directorio del script al path para encontrar aceid y copier
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

import aiohttp
from aiohttp import web, ClientSession
from aceid import AceIDManager     # Importación directa corregida
from copier import StreamCopier   # Importación directa corregida

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AceStream:
    def __init__(self, playback_url: str, stat_url: str, command_url: str, stream_id: str):
        self.playback_url = playback_url
        self.stat_url = stat_url
        self.command_url = command_url
        self.stream_id = stream_id

class OngoingStream:
    def __init__(self, stream_id: str, acestream: AceStream):
        self.stream_id = stream_id
        self.acestream = acestream
        self.clients = set()
        self.copier: Optional[StreamCopier] = None
        self.task: Optional[asyncio.Task] = None
        self.lock = asyncio.Lock()
        self.done = asyncio.Event()
        self.started = asyncio.Event()
        self.first_chunk = asyncio.Event()
        self.client_last_write = {}
        self.stopping = False

class AcexyProxy:
    def __init__(
            self,
            acestream_host: str = "localhost",
            acestream_port: int = 6878,
            scheme: str = "http",
            buffer_size: int = 4 * 1024 * 1024,
            m3u8_mode: bool = False,
            empty_timeout: float = 60.0,
            no_response_timeout: float = 1.0,
            stream_timeout: float = 60.0,
            write_timeout: float = 0.5,
    ):
        self.acestream_host = acestream_host
        self.acestream_port = acestream_port
        self.scheme = scheme
        self.buffer_size = buffer_size
        self.m3u8_mode = m3u8_mode
        self.empty_timeout = empty_timeout
        self.no_response_timeout = no_response_timeout
        self.stream_timeout = stream_timeout
        self.write_timeout = write_timeout
        self.endpoint = "/ace/manifest.m3u8" if m3u8_mode else "/ace/getstream"

        self.pid_manager = AceIDManager()
        self.streams: Dict[str, OngoingStream] = {}
        self.session: Optional[ClientSession] = None
        self.streams_lock = asyncio.Lock()
        
        # CABECERAS CORS
        self.cors_headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
        }

    async def _fetch_stream_info(self, stream_id: str, infohash: str, extra_params: dict) -> AceStream:
        temp_pid = str(uuid.uuid4())
        url = f"{self.scheme}://{self.acestream_host}:{self.acestream_port}{self.endpoint}"
        params = extra_params.copy()
        params['format'] = 'json'
        params['pid'] = temp_pid
        if stream_id: params['id'] = stream_id
        elif infohash: params['infohash'] = infohash
        else: raise ValueError("Either id or infohash must be provided")

        timeout = aiohttp.ClientTimeout(total=self.no_response_timeout)
        async with self.session.get(url, params=params, timeout=timeout) as response:
            if response.status != 200:
                raise Exception(f"AceStream middleware returned {response.status}")
            data = await response.json()
            if 'error' in data and data['error']:
                raise Exception(f"AceStream error: {data['error']}")
            resp = data['response']
            return AceStream(resp['playback_url'], resp.get('stat_url', ''), resp['command_url'], stream_id or infohash)

    async def _close_stream(self, acestream: AceStream):
        try:
            parsed = urlparse(acestream.command_url)
            query = parse_qs(parsed.query)
            query["method"] = ["stop"]
            url = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
            async with self.session.get(url) as response:
                pass
        except Exception as e:
            logger.warning(f"Exception while closing: {e}")

    async def _start_acestream_fetch(self, ongoing: OngoingStream):
        timeout = aiohttp.ClientTimeout(sock_read=self.empty_timeout)
        try:
            async with self.session.get(ongoing.acestream.playback_url, timeout=timeout) as ace_response:
                if ace_response.status != 200:
                    ongoing.started.set()
                    return
                ongoing.started.set()
                chunk_count = 0
                async for chunk in ace_response.content.iter_chunked(8192):
                    if not chunk or ongoing.stopping: break
                    chunk_count += 1
                    async with ongoing.lock:
                        client_list = list(ongoing.clients)
                    
                    dead_clients = []
                    successful_clients = []
                    current_time = asyncio.get_event_loop().time()
                    for client_res in client_list:
                        try:
                            await asyncio.wait_for(client_res.write(chunk), timeout=self.write_timeout)
                            successful_clients.append(client_res)
                        except:
                            dead_clients.append(client_res)

                    if successful_clients and chunk_count == 1: ongoing.first_chunk.set()
                    
                    async with ongoing.lock:
                        for c in successful_clients: ongoing.client_last_write[id(c)] = current_time
                        for d in dead_clients:
                            ongoing.clients.discard(d)
                            ongoing.client_last_write.pop(id(d), None)
                        if not ongoing.clients:
                            ongoing.stopping = True
                            break
        finally:
            await self._close_stream(ongoing.acestream)
            ongoing.done.set()
            async with self.streams_lock:
                if self.streams.get(ongoing.stream_id) is ongoing:
                    del self.streams[ongoing.stream_id]

    async def handle_options(self, request: web.Request) -> web.Response:
        """NUEVO: Manejador OPTIONS para CORS Preflight"""
        return web.Response(status=200, headers=self.cors_headers)

    async def handle_getstream(self, request: web.Request) -> web.StreamResponse:
        stream_id = request.query.get('id', '')
        infohash = request.query.get('infohash', '')

        if not stream_id and not infohash:
            return web.Response(status=400, text="Missing params", headers=self.cors_headers)

        key = stream_id or infohash
        async with self.streams_lock:
            if key not in self.streams or self.streams[key].done.is_set():
                try:
                    acestream = await self._fetch_stream_info(stream_id, infohash, {})
                    self.streams[key] = OngoingStream(key, acestream)
                except Exception as e:
                    return web.Response(status=500, text=str(e), headers=self.cors_headers)
            ongoing = self.streams[key]

        # Respuesta con cabeceras CORS
        response = web.StreamResponse(headers=self.cors_headers)
        response.content_type = 'application/x-mpegURL' if self.m3u8_mode else 'video/MP2T'
        if not self.m3u8_mode: response.headers['Transfer-Encoding'] = 'chunked'
        
        await response.prepare(request)

        async with ongoing.lock:
            ongoing.clients.add(response)
            if ongoing.task is None or ongoing.task.done():
                ongoing.task = asyncio.create_task(self._start_acestream_fetch(ongoing))

        try:
            await ongoing.done.wait()
        finally:
            async with ongoing.lock:
                ongoing.clients.discard(response)
            try: await response.write_eof()
            except: pass
        return response

    async def handle_status(self, request: web.Request) -> web.Response:
        """Handle /ace/status - Original + Full List con CORS"""
        stream_id = request.query.get('id', '')
        infohash = request.query.get('infohash', '')

        async with self.streams_lock:
            if not stream_id and not infohash:
                status_data = {"total_active_streams": len(self.streams), "streams": []}
                for key, ongoing in self.streams.items():
                    async with ongoing.lock:
                        status_data["streams"].append({
                            "id": key, "clients": len(ongoing.clients), "is_stopping": ongoing.stopping
                        })
                return web.json_response(status_data, headers=self.cors_headers)

            key = stream_id or infohash
            if key in self.streams:
                ongoing = self.streams[key]
                async with ongoing.lock:
                    status = {'clients': len(ongoing.clients), 'stream_id': key, 'is_stopping': ongoing.stopping}
                return web.json_response(status, headers=self.cors_headers)
            return web.Response(status=404, text="Not found", headers=self.cors_headers)

    async def start_server(self, host: str = "0.0.0.0", port: int = 8080):
        self.session = ClientSession()
        app = web.Application()
        
        # Rutas GET
        app.router.add_get('/ace/getstream', self.handle_getstream)
        app.router.add_get('/ace/getstream/', self.handle_getstream)
        app.router.add_get('/ace/status', self.handle_status)
        
        # Rutas OPTIONS para CORS
        app.router.add_options('/ace/getstream', self.handle_options)
        app.router.add_options('/ace/getstream/', self.handle_options)
        app.router.add_options('/ace/status', self.handle_options)

        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, host, port).start()
        logger.info(f"Server started on {host}:{port} with CORS & M3U8")
        try: await asyncio.Event().wait()
        finally:
            await self.session.close()
            await runner.cleanup()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("ACEXY_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("ACEXY_PORT", "6878")))
    parser.add_argument("--listen-addr", default=os.getenv("ACEXY_LISTEN_ADDR", ":8080"))
    parser.add_argument("--m3u8", action="store_true", default=os.getenv("ACEXY_M3U8", "").lower() == "true")
    args = parser.parse_args()
    
    lp = args.listen_addr.split(":")
    proxy = AcexyProxy(acestream_host=args.host, acestream_port=args.port, m3u8_mode=args.m3u8)
    try: asyncio.run(proxy.start_server(lp[0] or "0.0.0.0", int(lp[1]) if len(lp)>1 else 8080))
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
