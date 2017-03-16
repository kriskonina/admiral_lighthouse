import asyncio
import json
import sys
from aiohttp import web
from collections import deque, defaultdict

from docker import DockerClient
import io, os, pty
import pexpect, aiofiles

from aiohttp.web_ws import WSMsgType, MsgType

EMPTY_RECORD_MARKER = b'--'
MEMORY_UNIT_MULTIPLIER = {
    "B": .001,
    "kB": 1,
    "KiB": 1,
    "MiB": 1000,
    "MB": 1000,
    "GiB": 1000000,
    "GB": 1000000
}

def ratio_unit_parser(item):
    def parse_side(side_item):
        side_val, side_unit = side_item.split(" ")
        return float(side_val) * MEMORY_UNIT_MULTIPLIER[side_unit]
    leftside, rightside = item.split(" / ")
    return parse_side(leftside.strip()), parse_side(rightside.strip())

def parse_record_line(record):
    memory_raw = record['m'].split(" / ")[0].strip()
    memory_val, memory_unit = memory_raw.split(" ")
    kb_memory = float(memory_val.strip()) * MEMORY_UNIT_MULTIPLIER[memory_unit.strip()]

    kb_network_in, kb_network_out = ratio_unit_parser(record['n'])
    kb_disk_in, kb_disk_out = ratio_unit_parser(record['d'])
    return (
        float(record["c"].replace("%", "")), # cpu
        kb_memory,                           # memory usage in KB
        kb_network_in,                       # network incoming in KB
        kb_network_out,                      # network outcoming in KB
        kb_disk_in,                          # block writes in KB
        kb_disk_out,                         # block reads in KB
        int(record['p'].strip())             # PIDs
    )

class StatHolder:
    _stack = deque([], 2)
    _output = []

    @classmethod
    def append(cls, line):
        record = json.loads(line.strip())
        cls._output.append(parse_record_line(record))

    @classmethod
    def cap(cls):
        cls._stack.append(
            [sum(x) for x in zip(*cls._output)]
        )
        cls._output = []

    @classmethod
    def agg(cls):
        if not cls._stack:
            return []
        return cls._stack[-1]


async def resource_processor(app):
    cmd = ['docker',
           'stats',
           '--format',
           'table {"c":"{{.CPUPerc}}","m":"{{.MemUsage}}","n":"{{.NetIO}}","d":"{{.BlockIO}}","p":"{{.PIDs}}"}'
    ]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)

    # only for the first iteration
    # ignore the first line
    await process.stdout.readline()
    # harvest the other
    output = await process.stdout.readline()
    app.stat_holder.append(output.strip())

    while True:
        output = (await process.stdout.readline()).strip()
        if output:
            if EMPTY_RECORD_MARKER in output:
                # empty record, it happens even for running containers
                continue
            if output.startswith(b'\x1b[2J'):
                app.stat_holder.cap()
                # app.stat_holder.agg()
            else:
                app.stat_holder.append(output)
        # pause between calls
        asyncio.sleep(.1)

async def background_ps_kicker(app):
    app.resource_proc = app.loop.create_task(resource_processor(app))

async def background_ps_terminator(app):
    app.resource_proc.cancel()

async def statHandler(request):
    data = request.app.stat_holder.agg()
    return web.json_response(data)

async def executeHandler(request):
    # allow inbound connections from swarm nodes only
    # use that also to ensure 1 node = 1 socket

    # allow the maximum of 5 sockets per node
    ip = request.transport.get_extra_info('peername')[0]
    if len(request.app.websockets[ip]) == 4:
        raise web.HTTPTooManyRequests()

    container_id = request.match_info['container_id']
    cmd = request.match_info['cmd']

    async def emitter(kid, ws):
        fd = kid.fileno()
        async with aiofiles.open(fd, 'rb') as f:
            async for line in f:
                ws.send_bytes(line)

    ws = web.WebSocketResponse(heartbeat=10)
    await ws.prepare(request)

    try:
        request.app.websockets[ip].append(ws)
        kid = pexpect.spawn("docker exec -it {} sh".format(container_id))
        emitter_task = request.app.loop.create_task(emitter(kid, ws))

        async for msg in ws:
            if msg.tp == MsgType.text:
                if msg.data == 'close':
                    await ws.close()
                if msg.data == 'c+c':
                    kid.sendintr()
                    continue
                print("* Receiving bytes", msg.data)
                kid.sendline(msg.data)
            elif msg.tp == MsgType.error:
                print("receiving error: ", ws.exception(), flush=1)

    except Exception as exc:
        print("Exc", exc, flush=1)

    finally:
        emitter_task.cancel()
        request.app.websockets[ip].remove(ws)
        return ws

app = web.Application()
app.websockets = defaultdict(list)
app.stat_holder = StatHolder()
app.router.add_get('/stat', statHandler)
app.router.add_get('/exec/{container_id}/{cmd}', executeHandler)
app.on_startup.append(background_ps_kicker)
app.on_cleanup.append(background_ps_terminator)
web.run_app(app, host="0.0.0.0", port=1988)
