#!/usr/bin/env python3
"""
cansniffer_interactive.py - CAN sniffer e sender unificados.

Uso:
    cansniffer_interactive.py <interface> [--bitrate BITRATE]

<interface>: dispositivo SLCAN (ex: /dev/tty.usbserial-XXXX)
--bitrate: taxa CAN em bps (padrão: 500000 para VW Comfort)

Comandos em tempo de execução:
  q       - sair
  s       - enviar um frame (ex: 2B2#01 para destravar)
  c       - alternar cor on/off
  f       - limpar filtros
  +<ID>   - habilitar filtro para esse CAN ID (ex: +2B2)
  -<ID>   - desabilitar filtro para esse CAN ID (ex: -2B2)
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
parser.add_argument('interface', help='Dispositivo serial para a interface SLCAN (ex: /dev/cu.usbserial-XXXX)')
parser.add_argument('--backend', choices=['slcan'], default='slcan', help='Backend do python-can (apenas slcan suportado aqui)')
parser.add_argument('--bitrate', type=int, default=500000, help='Bitrate da rede CAN em bps (Padrão: 500000 para VW Comfort)')
args = parser.parse_args()

# --- Globais ---
stats = OrderedDict()
filters = set()
use_color = True
last_error = ""

# --- Regex para comandos ---
filter_re = re.compile(r'^([+-])([0-9A-Fa-f]{3,8})$')
frame_re = re.compile(r'^([0-9A-Fa-f]{3,8})#([0-9A-Fa-f]{0,16})$')

def open_bus():
    """Tenta abrir o barramento CAN."""
    global last_error
    try:
        bus = Bus(interface='slcan', channel=args.interface, bitrate=args.bitrate)
        last_error = ""
        return bus
    except Exception as e:
        last_error = f"Erro ao abrir bus: {e}"
        return None

def parse_and_send_frame(bus, frame_str):
    """Interpreta uma string como 'ID#DATA' e envia pelo barramento."""
    global last_error
    m = frame_re.match(frame_str)
    if not m:
        last_error = f"Formato de frame inválido: '{frame_str}'"
        return

    id_str, data_str = m.groups()
    try:
        can_id = int(id_str, 16)
        is_extended = len(id_str) > 3
        data = bytes.fromhex(data_str)
        if len(data) > 8:
            last_error = "Dados > 8 bytes!"
            return

        msg = Message(
            arbitration_id=can_id,
            data=data,
            is_extended_id=is_extended
        )
        bus.send(msg)
        last_error = f"Enviado: {frame_str.upper()}"
    except CanError as e:
        last_error = f"Erro ao enviar: {e}"
    except ValueError as e:
        last_error = f"Erro de valor: {e}"


def draw_screen(stdscr):
    """Desenha a tela principal do sniffer."""
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    # Cabeçalho
    header = " ID      Count   Last       Data (q=sair s=enviar c=cor +/-ID=filtro f=limpar)"
    try:
        stdscr.addstr(0, 0, header[:max_x - 1])
    except curses.error:
        return # Tela muito pequena

    # Linhas de dados
    row = 1
    # Filtra e ordena os IDs para exibição
    display_items = sorted(stats.items())
    
    for cid, entry in display_items:
        if row >= max_y - 2: break
        if filters and cid not in filters:
            continue

        line = f"{cid:>7} {entry['count']:>7}   {entry['last']:<8}   {entry['data']}"
        line = line[:max_x - 1] # Trunca a linha
        
        try:
            if use_color and entry.get('changed'):
                stdscr.addstr(row, 0, line, curses.color_pair(1))
                entry['changed'] = False # Reseta o destaque
            else:
                stdscr.addstr(row, 0, line)
        except curses.error:
            pass
        row += 1

    # Rodapé com status/erros
    status_bar = f"Filtros: {', '.join(sorted(list(filters))) if filters else 'Nenhum'} | {last_error}"
    try:
        stdscr.addstr(max_y - 1, 0, status_bar[:max_x - 1])
    except curses.error:
        pass

    stdscr.refresh()


def main(stdscr):
    global use_color, filters, last_error
    
    # Configuração do Curses
    curses.curs_set(0)
    stdscr.nodelay(True)
    if curses.has_colors():
        curses.start_color()
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)

    bus = open_bus()

    while True:
        # Tenta receber mensagem
        if bus:
            try:
                msg = bus.recv(timeout=0.05)
                if msg:
                    # (A lógica de recebimento de mensagens permanece a mesma)
                    cid = f"{msg.arbitration_id:0{8 if msg.is_extended_id else 3}X}"
                    data_str = ' '.join(f"{b:02X}" for b in msg.data)
                    now = time.strftime("%H:%M:%S")

                    if cid not in stats:
                        stats[cid] = {'data': '', 'count': 0, 'last': '', 'changed': False}
                    
                    entry = stats[cid]
                    if entry['data'] != data_str:
                        entry['changed'] = True
                        entry['data'] = data_str
                    
                    entry['count'] += 1
                    entry['last'] = now
            except Exception as e:
                bus.shutdown()
                bus = None
                last_error = f"Erro no recv: {e}"

        elif not bus:
            # Tenta reconectar
            time.sleep(1)
            bus = open_bus()

        # Desenha a tela
        draw_screen(stdscr)

        # Processa entrada do usuário
        try:
            key = stdscr.getch()
            if key != -1:
                # *** INÍCIO DA CORREÇÃO ***
                # Obter as dimensões da tela aqui, antes de usá-las.
                max_y, max_x = stdscr.getmaxyx()
                
                # chr(key) pode falhar para teclas especiais, melhor tratar com try-except
                try:
                    ch = chr(key)
                except ValueError:
                    ch = '' # Define como string vazia se for uma tecla não-imprimível

                if ch in ('q', 'Q'):
                    break
                
                elif ch in ('c', 'C'):
                    use_color = not use_color
                
                elif ch in ('f', 'F'):
                    filters.clear()
                    last_error = "Filtros limpos."

                elif ch in ('s', 'S'):
                    # Entra em modo de envio
                    curses.echo()
                    stdscr.nodelay(False)
                    
                    # Limpa a linha de status antes de escrever o prompt
                    status_line_y = max_y - 1
                    stdscr.addstr(status_line_y, 0, " " * (max_x - 1))
                    
                    prompt = "Enviar frame (ID#DADOS): "
                    stdscr.addstr(status_line_y, 0, prompt)
                    stdscr.refresh()

                    # Captura a string do usuário
                    frame_to_send = stdscr.getstr(status_line_y, len(prompt), 30).decode('utf-8')

                    curses.noecho()
                    stdscr.nodelay(True)

                    if frame_to_send and bus:
                        parse_and_send_frame(bus, frame_to_send)
                    else:
                        last_error = "Envio cancelado." # Mensagem se nada for digitado
                
                # (A lógica de filtro pode ser adicionada aqui se necessário)

        except curses.error:
            # Ignora erros de curses, como tentar escrever fora da tela
            pass
        except Exception as e:
            # Captura outros erros para não quebrar a aplicação
            last_error = f"Erro de input: {str(e)}"

    # Limpeza
    if bus:
        bus.shutdown()

if __name__ == '__main__':
    try:
        curses.wrapper(main)
    except Exception as e:
        print(f"Erro fatal: {e}")
        sys.exit(1)