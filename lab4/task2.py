#!/usr/bin/env python3
"""
ЛР4.№2 — Анализ длины Хаффман-кодов при разных разрядностях хранения частот.
"""

import sys
import math
from collections import Counter

def build_huffman_code_lengths(freqs):
    """Строим дерево Хаффмана и возвращаем длины кодов для каждого символа."""
    # очередь из пар (частота, список_символов)
    q = sorted([(f, [sym]) for sym, f in freqs.items()])
    lengths = {sym: 0 for sym in freqs}
    while len(q) > 1:
        f1, syms1 = q.pop(0)
        f2, syms2 = q.pop(0)
        for s in syms1: lengths[s] += 1
        for s in syms2: lengths[s] += 1
        q.append((f1+f2, syms1+syms2))
        q.sort()
    return lengths

def normalize_freqs(freqs, B):
    """Нормализуем частоты в диапазон 0..2^B-1 (не обнуляя ненулевые)."""
    max_val = (1 << B) - 1
    max_freq = max(freqs.values())
    if max_freq <= max_val:
        return dict(freqs)  # влезает без нормализации
    scaled = {}
    for sym, f in freqs.items():
        val = max(1, round(f * max_val / max_freq))  # ноль -> 0, ненулевые -> ≥1
        scaled[sym] = val
    return scaled

def huffman_length(data, B):
    """Возвращает E_B (длина сжатых данных в байтах) и G_B (с учётом таблицы частот)."""
    freqs = Counter(data)
    freqsB = normalize_freqs(freqs, B)
    lengths = build_huffman_code_lengths(freqsB)
    # длина кодированного текста в битах
    total_bits = sum(freqs[sym] * lengths[sym] for sym in freqs)
    E = (total_bits + 7) // 8
    G = E + 32 * B  # служебные данные
    return E, G

def analyze_file(path, B_values=(64,32,8,4)):
    with open(path, "rb") as f:
        data = f.read()
    print(f"\nФайл: {path}, размер {len(data)} байт")
    results = {}
    for B in B_values:
        E, G = huffman_length(data, B)
        results[B] = (E, G)
        print(f"B={B:2d}: E_B={E} байт, G_B={G} байт")
    # выбираем оптимальное
    bestB = min(results, key=lambda B: results[B][1])
    print(f"Оптимальная разрядность: B*={bestB}, G_B*={results[bestB][1]} байт")
    return results

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python l4_2.py file1 [file2 ...]")
        sys.exit(1)
    for path in sys.argv[1:]:
        analyze_file(path)
#py task2.py test_text.txt test_bin.bin 