#!/usr/bin/env python3
"""
cansniffer_interactive.py - CAN sniffer e sender unificados com modo gerador.

Uso:
    cansniffer_interactive.py <interface> [--bitrate BITRATE]

Comandos em tempo de execução:
  q       - sair
  s       - enviar um frame (uma vez)
  g       - gerar um frame ciclicamente (cangen)
  p       - parar todos os geradores
  c       - alternar cor on/off
  f       - limpar filtros
  +<ID>   - habilitar filtro para esse CAN ID
  -<ID>   - desabilitar filtro para esse CAN ID
"""
import sys
import re
import time
import curses
from collections import OrderedDict
from can import Bus, Message, CanError
import argparse

# --- Argumentos ---
parser = argparse.ArgumentParser(description='CAN Sniffer e Sender interativo via SLCAN.')
parser.add_argument('interface', help='Dispositivo serial para a interface SLCAN')
parser.add_argument('--bitrate', type=int, default=500000, help='Bitrate da rede CAN em bps')
args = parser.parse_args()

# --- Globais ---
stats = OrderedDict()
filters = set()
use_color = True
last_error = ""
# Dicionário para armazenar mensagens cíclicas: { 'ID#DATA': {'interval': 0.1, 'last_sent': 0} }
cyclical_messages = {}

# --- Regex para comandos ---
frame_re = re.compile(r'^([0-9A-Fa-f]{3,8})#([0-9A-Fa-f]{0,16})$')

def open_bus():
    # (Esta função permanece a mesma)
    global last_error
    try:
        bus = Bus(interface='slcan', channel=args.interface, bitrate=args.bitrate)
        last_error = ""
        return bus
    except Exception as e:
        last_error = f"Erro ao abrir bus: {e}"
        return None

def parse_frame_string(frame_str):
    """Interpreta uma string 'ID#DATA' e retorna um objeto Message."""
    m = frame_re.match(frame_str)
    if not m:
        raise ValueError(f"Formato inválido: '{frame_str}'")

    id_str, data_str = m.groups()
    can_id = int(id_str, 16)
    is_extended = len(id_str) > 3
    data = bytes.fromhex(data_str) if data_str else b''
    
    if len(data) > 8:
        raise ValueError("Dados > 8 bytes!")

    return Message(arbitration_id=can_id, data=data, is_extended_id=is_extended)

def draw_screen(stdscr):
    # (Esta função permanece a mesma, mas com cabeçalho atualizado)
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()
    
    header = " ID      Count   Last       Data (q=sair s=send g=gen p=purge c=cor +/-ID=filt)"
    try:
        stdscr.addstr(0, 0, header[:max_x - 1])
    except curses.error:
        return

    # (Restante da função de desenho é igual)
    row = 1
    display_items = sorted(stats.items())
    for cid, entry in display_items:
        if row >= max_y - 2: break
        if filters and cid not in filters:
            continue
        line = f"{cid:>7} {entry['count']:>7}   {entry['last']:<8}   {entry['data']}"
        line = line[:max_x - 1]
        try:
            if use_color and entry.get('changed'):
                stdscr.addstr(row, 0, line, curses.color_pair(1))
                entry['changed'] = False
            else:
                stdscr.addstr(row, 0, line)
        except curses.error:
            pass
        row += 1

    # Rodapé com status
    gen_status = f"Gerando: {', '.join(cyclical_messages.keys())}" if cyclical_messages else "Geradores: 0"
    status_bar = f"{gen_status} | {last_error}"
    try:
        stdscr.addstr(max_y - 1, 0, status_bar[:max_x - 1], curses.A_REVERSE)
    except curses.error:
        pass

    stdscr.refresh()

def main(stdscr):
    global use_color, filters, last_error, cyclical_messages
    
    curses.curs_set(0)
    stdscr.nodelay(True)
    if curses.has_colors():
        curses.start_color()
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)

    bus = open_bus()

    while True:
        now = time.time()
        
        # --- NOVO: Processa geradores cíclicos ---
        if bus:
            for frame_str, details in cyclical_messages.items():
                if now - details['last_sent'] >= details['interval']:
                    try:
                        msg = parse_frame_string(frame_str)
                        bus.send(msg)
                        details['last_sent'] = now
                    except Exception as e:
                        last_error = f"Erro no gerador: {e}"

        # Tenta receber mensagem (mesma lógica de antes)
        if bus:
            try:
                msg = bus.recv(timeout=0.02) # Timeout pequeno para não bloquear
                if msg:
                    # Lógica de atualização do 'stats'
                    cid = f"{msg.arbitration_id:0{8 if msg.is_extended_id else 3}X}"
                    data_str = ' '.join(f"{b:02X}" for b in msg.data)
                    timestamp = time.strftime("%H:%M:%S")

                    if cid not in stats:
                        stats[cid] = {'data': '', 'count': 0, 'last': '', 'changed': False}
                    
                    entry = stats[cid]
                    if entry['data'] != data_str:
                        entry['changed'] = True
                        entry['data'] = data_str
                    
                    entry['count'] += 1
                    entry['last'] = timestamp
            except Exception as e:
                bus.shutdown()
                bus = None
                last_error = f"Erro no recv: {e}"

        elif not bus:
            time.sleep(1)
            bus = open_bus()

        draw_screen(stdscr)

        # Processa entrada do usuário
        try:
            key = stdscr.getch()
            if key != -1:
                max_y, max_x = stdscr.getmaxyx()
                ch = chr(key) if key < 256 else ''

                # --- Comandos ---
                if ch in ('q', 'Q'): break
                elif ch in ('c', 'C'): use_color = not use_color
                elif ch in ('f', 'F'):
                    filters.clear()
                    last_error = "Filtros limpos."
                elif ch in ('p', 'P'): # NOVO: Purge generators
                    cyclical_messages.clear()
                    last_error = "Geradores parados."
                
                elif ch in ('s', 'S') or ch in ('g', 'G'): # Send or Generate
                    is_generator = ch in ('g', 'G')
                    
                    # --- Lógica de prompt de usuário ---
                    curses.echo()
                    stdscr.nodelay(False)
                    
                    prompt_y = max_y - 1
                    stdscr.addstr(prompt_y, 0, " " * (max_x - 1), curses.A_REVERSE)
                    
                    prompt_frame = "Frame (ID#DADOS): "
                    stdscr.addstr(prompt_y, 0, prompt_frame, curses.A_REVERSE)
                    stdscr.refresh()
                    frame_to_send = stdscr.getstr(prompt_y, len(prompt_frame), 30).decode('utf-8').upper()

                    interval_ms = "100" # Default interval for generators
                    if is_generator and frame_to_send:
                        prompt_interval = f"Intervalo em ms (padrão {interval_ms}): "
                        stdscr.addstr(prompt_y, 0, " " * (max_x - 1), curses.A_REVERSE)
                        stdscr.addstr(prompt_y, 0, prompt_interval, curses.A_REVERSE)
                        stdscr.refresh()
                        user_interval = stdscr.getstr(prompt_y, len(prompt_interval), 5).decode('utf-8')
                        if user_interval.isdigit():
                            interval_ms = user_interval

                    curses.noecho()
                    stdscr.nodelay(True)

                    # --- Execução do comando ---
                    if frame_to_send:
                        try:
                            # Apenas valida o formato, não envia ainda
                            msg = parse_frame_string(frame_to_send)
                            if is_generator:
                                interval_sec = int(interval_ms) / 1000.0
                                cyclical_messages[frame_to_send] = {'interval': interval_sec, 'last_sent': 0}
                                last_error = f"Gerando {frame_to_send} a cada {interval_ms}ms"
                            elif bus:
                                bus.send(msg)
                                last_error = f"Enviado: {frame_to_send}"
                        except Exception as e:
                            last_error = f"Erro: {e}"
                    else:
                        last_error = "Envio cancelado."

        except Exception: pass # Ignora erros de input

    if bus: bus.shutdown()

if __name__ == '__main__':
    try:
        curses.wrapper(main)
    except curses.error as e:
        print(f"Erro de Curses: {e}. A janela do terminal é muito pequena?")
    except Exception as e:
        print(f"Erro fatal: {e}")