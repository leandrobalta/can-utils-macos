#!/usr/bin/env python3
"""
cansniffer.py - volatile CAN content visualizer via python-can

Uso:
    cansniffer.py <interface> [--backend {slcan,socketcan}] [--bitrate BITRATE]

<interface>: dispositivo SLCAN (ex: /dev/ttyUSB0) ou interface socketCAN (ex: can0)
--backend: escolha "slcan" para usar serial, ou "socketcan" para usar SocketCAN (padrão: socketcan)
--bitrate: taxa CAN em bps (apenas para slcan, padrão: 500000)

Comandos em tempo de execução:
  q       - sair
  +<ID>   - habilitar filtro para esse CAN ID
  -<ID>   - desabilitar filtro para esse CAN ID
  c       - alternar cor on/off

Exemplo:
  # Usando SocketCAN
  cansniffer.py can0 --backend socketcan
  # Usando SLCAN serial
  cansniffer.py /dev/ttyUSB0 --backend slcan --bitrate 500000
"""
import sys
import re
import time
import curses
from collections import OrderedDict
from can import Bus, CanError
import argparse

# Parser de argumentos
t = argparse.ArgumentParser(prog='cansniffer.py')
t.add_argument('interface', help='Serial device ou CAN interface')
t.add_argument('--backend', choices=['slcan','socketcan'], default='socketcan',
               help='slcan=serial, socketcan=SocketCAN')
t.add_argument('--bitrate', type=int, default=500000,
               help='bitrate para SLCAN (bps)')
args = t.parse_args()

# Dados do sniffer
stats = OrderedDict()   # { '3E8': {data, count, last, changed} }
filters = set()         # IDs habilitados; vazio = todos
use_color = True
cmd_re = re.compile(r'^([+-])([0-9A-Fa-f]{3,8})$')

# Abre bus conforme backend
def open_bus():
    if args.backend == 'slcan':
        return Bus(interface='slcan', channel=args.interface, bitrate=args.bitrate)
    else:
        return Bus(interface='socketcan', channel=args.interface)

# Inicializa bus
try:
    bus = open_bus()
except Exception as e:
    print(f"Erro ao abrir '{args.interface}' [{args.backend}]: {e}")
    sys.exit(1)

# Desenha tabela em curses com tamanho dinâmico e captura curses.error
def draw_table(stdscr):
    stdscr.erase()
    # Cabeçalho
    try:
        stdscr.addstr(0, 0, " ID   Count   Last     Data   (q=quit, +ID/-ID filtrar, c=color)")
    except curses.error:
        return

    # Linhas disponíveis
    max_y, max_x = stdscr.getmaxyx()
    row = 1
    for cid, entry in stats.items():
        if row >= max_y:
            break  # sem mais espaço
        if filters and cid not in filters:
            continue
        line = f"{cid:>3}   {entry['count']:>5}   {entry['last']:>8}   {entry['data']}"
        # Trunca para largura da tela
        line = line[:max_x-1]
        try:
            if use_color and entry.get('changed'):
                stdscr.addstr(row, 0, line, curses.color_pair(1))
            else:
                stdscr.addstr(row, 0, line)
        except curses.error:
            pass
        row += 1
    stdscr.refresh()

# Loop principal
def main(stdscr):
    global bus, use_color
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)

    while True:
        # Try recv, reconecta em caso de erro
        try:
            msg = bus.recv(timeout=0.2)
        except Exception:
            try:
                bus.shutdown()
            except:
                pass
            time.sleep(1)
            # tenta reconectar
            while True:
                try:
                    bus = open_bus()
                    break
                except Exception:
                    time.sleep(1)
            continue

        # Atualiza stats
        if msg:
            cid = f"{msg.arbitration_id:03X}"
            data_str = ' '.join(f"{b:02X}" for b in msg.data)
            now = time.strftime("%H:%M:%S")
            if cid not in stats:
                stats[cid] = {'data': '', 'count': 0, 'last': '', 'changed': False}
            entry = stats[cid]
            entry['changed'] = (entry['data'] != data_str)
            entry['data']    = data_str
            entry['count']  += 1
            entry['last']    = now

        # Renderização
        draw_table(stdscr)

        # Entrada de usuário
        try:
            ch = stdscr.getkey()
        except Exception:
            ch = None

        if ch in ('q', 'Q'):
            break
        m = cmd_re.match(ch or '')
        if m:
            sign, id_raw = m.groups()
            cid = id_raw.upper().zfill(3)
            if sign == '+':
                filters.add(cid)
            else:
                filters.discard(cid)
        elif ch in ('c', 'C'):
            use_color = not use_color

    # Limpa
    try:
        bus.shutdown()
    except:
        pass

if __name__ == '__main__':
    curses.wrapper(main)
