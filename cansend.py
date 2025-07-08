#!/usr/bin/env python3
"""
cansend.py - envia frames CAN via python-can (SLCAN)

Usage:
    cansend.py <serial_device> <can_frame>

<serial_device>: porta serial do Arduino (ex: /dev/cu.usbserial-A5069RR4)
<can_frame>:
    <can_id>#{data}     para frames CAN 2.0B de dados
    <can_id>#R{len}     para frames RTR

Exemplos:
    cansend.py /dev/cu.usbserial-A5069RR4 123#DEADBEEF
    cansend.py /dev/cu.usbserial-A5069RR4 470#00005DFF00
    cansend.py /dev/cu.usbserial-A5069RR4 321#R
"""
import sys
import re
from can import Bus, Message, CanError

def print_usage(prog):
    print(f"Uso: {prog} <serial_device> <can_frame>")
    print("Exemplo: 123#DEADBEEF para dados, 321#R para RTR")
    sys.exit(1)

# corresponde a <ID>#{DATA} ou <ID>#R{LEN}
frame_re = re.compile(r'^([0-9A-Fa-f]{3,8})#([0-9A-Fa-f\.]{0,16}|[Rr][0-9]?)$')

def parse_frame(frame_str):
    m = frame_re.match(frame_str)
    if not m:
        raise ValueError(f"Formato inválido: '{frame_str}'")
    id_str, data_str = m.groups()
    can_id = int(id_str, 16)
    is_ext = len(id_str) > 3
    # RTR?
    if data_str and data_str[0] in 'Rr':
        is_rtr = True
        dlc = int(data_str[1], 16) if len(data_str) > 1 else 0
        data = []
    else:
        is_rtr = False
        hex_str = data_str.replace('.', '')
        if len(hex_str) % 2 != 0:
            raise ValueError("Hex de dados deve ter número par de dígitos")
        data = [int(hex_str[i:i+2], 16) for i in range(0, len(hex_str), 2)]
        dlc = len(data)
    if dlc > 8:
        raise ValueError("DLC inválido (máximo 8)")
    return id_str.upper(), can_id, is_ext, is_rtr, dlc, data


def main():
    if len(sys.argv) != 3:
        print_usage(sys.argv[0])

    device = sys.argv[1]
    frame_str = sys.argv[2]

    try:
        id_str, can_id, is_ext, is_rtr, dlc, data = parse_frame(frame_str)
    except Exception as e:
        print(f"Erro: {e}")
        print_usage(sys.argv[0])

    try:
        bus = Bus(interface='slcan', channel=device, bitrate=500000)
    except Exception as e:
        print(f"Não foi possível abrir {device}: {e}")
        sys.exit(1)

    msg = Message(
        arbitration_id=can_id,
        data=data,
        is_extended_id=is_ext,
        is_remote_frame=is_rtr
    )
    try:
        bus.send(msg)
        # saída estilo cansend
        if is_rtr:
            suffix = 'R' + (f"{dlc:X}" if dlc else '')
            print(f"{id_str}#{suffix} enviado")
        else:
            hex_data = ''.join(f"{b:02X}" for b in data)
            print(f"{id_str}#{hex_data} enviado")
    except CanError as e:
        print(f"Falha ao enviar: {e}")
        sys.exit(1)
    finally:
        bus.shutdown()

if __name__ == '__main__':
    main()
