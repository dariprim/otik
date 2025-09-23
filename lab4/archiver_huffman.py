#!/usr/bin/env python3
"""
L4.№1 — Архиватор с поддержкой кодирования Хаффмана.

Формат основан на L3ARCH02, но версия и сигнатура изменены:
- SIGNATURE = b'L3ARCH04'
- VERSION   = 2

Добавлен новый алгоритм сжатия без контекста:
- ALG_NOCTX_HUFFMAN = 3 (кодирование Хаффмана).

Поддерживается CRC32 (ALG_PROT = 11).
"""

import struct
import sys
import os
import argparse
import heapq
from pathlib import Path
from collections import Counter
from binascii import crc32

# === Константы формата ===
SIGNATURE = b'L3ARCH04'           # сигнатура для ЛР4
SIGNATURE_PREFIX = b'L3ARCH'      # проверяем первые 6 байт
VERSION = 2                       # версия формата ↑

# Коды алгоритмов (без контекста)
ALG_NOCTX_NONE = 0
ALG_NOCTX_ZLIB = 2        # оставлен из ЛР3
ALG_NOCTX_HUFFMAN = 3     # новый код для Хаффмана

# Коды защиты
ALG_PROT_NONE = 0
ALG_PROT_CRC32 = 11

RESERVED = 0

# Типы записей
ENTRY_DIR = 0
ENTRY_FILE = 1
MAX_PATH_DEPTH = 4  # ограничение глубины

# =====================================================
# === Реализация кодирования/декодирования Хаффмана ===
# =====================================================

class Node:
    """Узел дерева Хаффмана."""
    def __init__(self, freq, symbol=None, left=None, right=None):
        self.freq = freq        # частота
        self.symbol = symbol    # байт (0–255) или None для внутреннего узла
        self.left = left
        self.right = right

    def __lt__(self, other):
        """
        Сравнение узлов для heapq.
        При равных частотах — по байтовому значению,
        чтобы дерево строилось детерминированно.
        """
        if self.freq == other.freq:
            return (self.symbol or 0) < (other.symbol or 0)
        return self.freq < other.freq


def build_huffman_tree(freqs):
    """Строит дерево Хаффмана по словарю {символ: частота}."""
    heap = [Node(fr, sym) for sym, fr in freqs.items()]
    heapq.heapify(heap)
    if len(heap) == 1:
        # крайний случай: один символ
        only = heap[0]
        return Node(only.freq, None, only, None)
    while len(heap) > 1:
        a = heapq.heappop(heap)
        b = heapq.heappop(heap)
        new = Node(a.freq + b.freq, None, a, b)
        heapq.heappush(heap, new)
    return heap[0]


def build_codes(node, prefix="", codebook=None):
    """Рекурсивно обходит дерево и строит кодовую таблицу {символ: битовая строка}."""
    if codebook is None:
        codebook = {}
    if node.symbol is not None:
        # Листовой узел — назначаем код
        codebook[node.symbol] = prefix or "0"
    else:
        build_codes(node.left, prefix + "0", codebook)
        build_codes(node.right, prefix + "1", codebook)
    return codebook


def huffman_encode(data: bytes):
    """
    Кодирование массива байт методом Хаффмана.
    Возвращает (закодированные_данные, служебные_данные).
    """
    freqs = Counter(data)              # частоты символов
    root = build_huffman_tree(freqs)   # строим дерево
    codebook = build_codes(root)       # таблица кодов

    # Строим битовую строку
    bits = "".join(codebook[b] for b in data)
    # Выравнивание до байта
    padding = (8 - len(bits) % 8) % 8
    bits += "0" * padding
    encoded = int(bits, 2).to_bytes(len(bits) // 8, "big")

    # === Служебные данные ===
    # padding (2 байта), число символов (2 байта), затем список (символ, частота)
    service = struct.pack("<H", padding)
    service += struct.pack("<H", len(freqs))
    for sym, fr in freqs.items():
        service += struct.pack("<BI", sym, fr)

    return encoded, service


def huffman_decode(encoded: bytes, service: bytes, orig_size: int):
    """
    Декодирование массива байт методом Хаффмана.
    Использует таблицу частот из service.
    """
    # Читаем padding и число символов
    padding, = struct.unpack_from("<H", service, 0)
    num_syms, = struct.unpack_from("<H", service, 2)
    freqs = {}
    offset = 4
    for _ in range(num_syms):
        sym, fr = struct.unpack_from("<BI", service, offset)
        offset += 5
        freqs[sym] = fr

    root = build_huffman_tree(freqs)

    # Читаем битовую строку
    bitstr = bin(int.from_bytes(encoded, "big"))[2:].zfill(len(encoded) * 8)
    if padding:
        bitstr = bitstr[:-padding]

    # Декодируем по дереву
    out = bytearray()
    node = root
    for bit in bitstr:
        node = node.left if bit == "0" else node.right
        if node.symbol is not None:
            out.append(node.symbol)
            node = root
            if len(out) == orig_size:
                break
    return bytes(out)

# =====================================================
# === Архиватор (аналог Л3, но с поддержкой Хаффмана) ==
# =====================================================

def _check_depth_ok(rel_path: str):
    """Проверка глубины вложенности пути (≤ 4)."""
    depth = rel_path.count('/')
    return depth <= (MAX_PATH_DEPTH - 1)


def collect_entries(inputs):
    """Собирает список файлов для архивации (без директорий для упрощения)."""
    entries, seen_paths = [], set()
    for inp in inputs:
        p = Path(inp)
        if not p.exists():
            continue
        if p.is_file():
            rel = p.name
            if rel not in seen_paths:
                entries.append({'type': ENTRY_FILE, 'relpath': rel,
                                'orig_path': str(p.resolve()), 'orig_size': p.stat().st_size})
                seen_paths.add(rel)
        else:
            for root, _, files in os.walk(p):
                root_path = Path(root)
                rel_root = root_path.relative_to(p)
                for fname in files:
                    rel = os.path.join(str(rel_root), fname) if str(rel_root) != '.' else fname
                    rel_unix = rel.replace('\\', '/')
                    if rel_unix not in seen_paths:
                        fpath = root_path / fname
                        entries.append({'type': ENTRY_FILE, 'relpath': rel_unix,
                                        'orig_path': str(fpath.resolve()), 'orig_size': fpath.stat().st_size})
                        seen_paths.add(rel_unix)
    return entries


def build_archive(entries, out_path, huffman=False, crc=False):
    """Собирает архив."""
    alg_noctx = ALG_NOCTX_HUFFMAN if huffman else ALG_NOCTX_NONE
    alg_prot = ALG_PROT_CRC32 if crc else ALG_PROT_NONE

    data_blocks, entry_service, stored_sizes, orig_sizes = [], [], [], []

    # Кодируем каждую запись
    for ent in entries:
        with open(ent['orig_path'], 'rb') as f:
            raw = f.read()
        orig_size = len(raw)

        if huffman:
            stored, service = huffman_encode(raw)
        else:
            stored, service = raw, b''

        if crc:
            # добавляем CRC32 в конец служебных данных
            service += struct.pack('<I', crc32(raw) & 0xffffffff)

        stored_sizes.append(len(stored))
        orig_sizes.append(orig_size)
        entry_service.append(service)
        data_blocks.append(stored)

    # === Таблица записей ===
    FIXED_HEADER_LEN = 8 + 2 + 1 + 1 + 1 + 1 + 8 + 4
    table_bytes = bytearray()
    for i, ent in enumerate(entries):
        relpath_bytes = ent['relpath'].encode('utf-8')
        service_bytes = entry_service[i]
        table_bytes += struct.pack('<B', ent['type'])
        table_bytes += struct.pack('<H', len(relpath_bytes))
        table_bytes += relpath_bytes
        table_bytes += struct.pack('<Q', orig_sizes[i])
        table_bytes += struct.pack('<Q', stored_sizes[i])
        table_bytes += struct.pack('<I', len(service_bytes))
        table_bytes += service_bytes

    header_size = FIXED_HEADER_LEN + len(table_bytes)

    # === Сборка архива ===
    with open(out_path, 'wb') as out:
        out.write(SIGNATURE)
        out.write(struct.pack('<H', VERSION))
        out.write(struct.pack('<B', 0))  # ALG_CTX (не используем)
        out.write(struct.pack('<B', alg_noctx))
        out.write(struct.pack('<B', alg_prot))
        out.write(struct.pack('<B', RESERVED))
        out.write(struct.pack('<Q', header_size))
        out.write(struct.pack('<I', len(entries)))
        out.write(table_bytes)
        for block in data_blocks:
            out.write(block)

    print(f"Архив '{out_path}' создан. alg_noctx={alg_noctx} (3=HUFFMAN), alg_prot={alg_prot}")


def extract_archive(archive_path, out_dir):
    """Распаковка архива."""
    with open(archive_path, 'rb') as f:
        sig = f.read(8)
        if sig[:6] != SIGNATURE_PREFIX:
            raise ValueError("Неверная сигнатура")
        version = struct.unpack('<H', f.read(2))[0]
        alg_ctx = f.read(1)[0]
        alg_noctx = f.read(1)[0]
        alg_prot = f.read(1)[0]
        _ = f.read(1)
        header_size = struct.unpack('<Q', f.read(8))[0]
        num_entries = struct.unpack('<I', f.read(4))[0]

        # Читаем метаданные записей
        entries_meta = []
        for _ in range(num_entries):
            entry_type = f.read(1)[0]
            path_len = struct.unpack('<H', f.read(2))[0]
            relpath = f.read(path_len).decode('utf-8')
            orig_size = struct.unpack('<Q', f.read(8))[0]
            stored_size = struct.unpack('<Q', f.read(8))[0]
            service_len = struct.unpack('<I', f.read(4))[0]
            service = f.read(service_len) if service_len else b''
            entries_meta.append((entry_type, relpath, orig_size, stored_size, service))

        out_dir_path = Path(out_dir)
        out_dir_path.mkdir(parents=True, exist_ok=True)

        # Восстанавливаем файлы
        for entry_type, relpath, orig_size, stored_size, service in entries_meta:
            target_path = out_dir_path / Path(relpath)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            stored_bytes = f.read(stored_size) if stored_size else b''

            if entry_type == ENTRY_FILE:
                if alg_noctx == ALG_NOCTX_HUFFMAN:
                    # отделяем CRC если есть
                    crc_val = None
                    if alg_prot == ALG_PROT_CRC32 and len(service) > 6:
                        crc_val = struct.unpack('<I', service[-4:])[0]
                        service = service[:-4]
                    raw = huffman_decode(stored_bytes, service, orig_size)
                    if crc_val is not None:
                        if (crc32(raw) & 0xffffffff) != crc_val:
                            print(f"CRC mismatch for {relpath}")
                else:
                    raw = stored_bytes

                with open(target_path, 'wb') as outf:
                    outf.write(raw)
                print(f"Восстановлен: {relpath}")


def main():
    parser = argparse.ArgumentParser(description="L4.№1 Huffman Archiver")
    sub = parser.add_subparsers(dest='cmd')

    # Кодирование
    enc = sub.add_parser('encode', help='Create archive')
    enc.add_argument('inputs', nargs='+')
    enc.add_argument('-o', '--out', required=True)
    enc.add_argument('--huffman', action='store_true', help='Включить сжатие Хаффмана')
    enc.add_argument('--crc', action='store_true', help='Добавить CRC32')

    # Декодирование
    dec = sub.add_parser('decode', help='Extract archive')
    dec.add_argument('archive')
    dec.add_argument('-d', '--outdir', default='.')

    args = parser.parse_args()
    if args.cmd == 'encode':
        entries = collect_entries(args.inputs)
        build_archive(entries, args.out, huffman=args.huffman, crc=args.crc)
    elif args.cmd == 'decode':
        extract_archive(args.archive, args.outdir)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
#Compare-Object (Get-Content test_text.txt) (Get-Content outdir/test_text.txt) для сравнения, если ничего не показал - все ок