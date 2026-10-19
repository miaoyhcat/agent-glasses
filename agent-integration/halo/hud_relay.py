#!/usr/bin/env python3
"""Optional real Halo SDK HUD relay. Import/signature checked; no hardware tested.

Use a paired device token; never supply the desktop operator token.
Shows task metadata, not source code, shell arguments or private reasoning.
"""
import argparse
import asyncio
from datetime import datetime
from pathlib import Path
import ssl
import re
from aiohttp import ClientSession


def lua_string(text):
    # Lua decimal byte escapes; hostile quotes/newlines cannot become Lua statements.
    return '"'+''.join('\\'+f'{b:03d}' for b in text.encode('utf-8'))+'"'


def commands(project,status,clock):
    project=str(project)[:18];status=str(status)[:18]
    return ['frame.display.clear()', 'frame.display.set_font(0,16,1)',
        f'frame.display.text({lua_string(clock)},38,45,0xFFFFFF)',
        f'frame.display.text({lua_string(project)},24,100,0xFFFFFF)',
        f'frame.display.text({lua_string(status)},24,140,0x88FFAA)']


async def main(args):
    from brilliant_ble import BrilliantBle
    from urllib.parse import urlparse
    parsed=urlparse(args.desktop)
    if parsed.scheme!='https' or parsed.username or parsed.path not in {'','/'}:
        raise ValueError('HTTPS origin required')
    if not re.fullmatch(r'Halo [A-Fa-f0-9]{2}',args.name):raise ValueError('Use the exact Halo XX name')
    trust=ssl.create_default_context(cafile=str(args.certificate));token=args.token_file.read_text().strip()
    frame=BrilliantBle();last=None
    try:
        await frame.connect(name=args.name)
        async with ClientSession(headers={'Authorization':'Bearer '+token}) as session:
            while True:
                async with session.get(args.desktop.rstrip('/')+'/v1/tasks',ssl=trust,allow_redirects=False) as response:
                    if response.status!=200:raise RuntimeError('Desktop authentication/connection failed')
                    tasks=(await response.json())['tasks']
                task=tasks[0] if tasks else {'project':'CodexGlasses','status':'no tasks'}
                state=(task['project'],task['status'],datetime.now().strftime('%H:%M'))
                if state!=last:
                    for command in commands(*state):
                        if len(command.encode())>frame.max_lua_payload():raise RuntimeError('Negotiated BLE payload too small')
                        await frame.send_lua(command)
                    last=state
                await asyncio.sleep(2)
    finally:
        await frame.disconnect()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--desktop',required=True);p.add_argument('--certificate',required=True,type=Path)
    p.add_argument('--token-file',required=True,type=Path);p.add_argument('--name',required=True)
    asyncio.run(main(p.parse_args()))
