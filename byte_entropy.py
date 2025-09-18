#!/usr/bin/env python3
"""
byte_entropy.py

Считает частотности по байтам файла, оценивает модель без памяти (iid):
- n: длина файла в байтах
- count(j) для j=0..255
- p(j) = count(j)/n
- I(j) = -log2(p(j)) [бит]
- I(Q) = sum_j count(j) * I(j)  (суммарное количество информации в файле)

Печатает:
- L(Q) [бит] = n*8 и сравнение с I(Q) [бит]
- I(Q) [бит] с двумя знаками после запятой и дробную часть в экспоненциальной форме
- L(Q) [октетов] = n и I(Q) [октетов] = I(Q)[бит]/8 с двумя знаками
- E = ceil(I_octets)
- G64 = E + 256*8
- G8  = E + 256*1

Генерирует таблицы символов (256 строк) в двух сортировках:
- по значению байта (00..FF)
- по убыванию count

Сохраняет текстовый отчёт (report) по умолчанию "report.txt".

Пример запуска:
    python3 byte_entropy.py input.bin -o report.txt

Для проверки корректности:
- на файле из одинаковых байтов (например, только 0xAA) должно быть I_BP(Q)=0,
- на файле с четырьмя разными октетами a,b,c,d каждый по одному разу: I_BP(Q)=8 бит (1 байт).

Скрипт также умеет создавать тестовые файлы различных форматов:
    python3 byte_entropy.py --make-tests

Будут созданы:
- test_text.txt (текстовый файл)
- test_bin.bin (бинарный файл с равномерным распределением байтов)
- test_repeated.bin (монотонный файл из одного байта)
- test_small.bin (контрольный маленький файл a,b,c,d)

Вопросы анализа:
- Выгодно ли сжатие без учёта контекста? Обычно нет на случайных/бинарных файлах, но да на текстах с большой избыточностью.
- Нужно ли нормировать частоты? Для энтропии используются именно нормированные вероятности p(j)=count(j)/n; ненормированные частоты нужны для хранения модели (таблицы). В реальных архивах нормировка обязательна.

"""

import sys
import argparse
from collections import Counter
import math
from datetime import datetime
import os


def analyze_file(path):
    counts = [0]*256
    n = 0
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            n += len(chunk)
            for b in chunk:
                counts[b] += 1
    return n, counts


def format_hex(b):
    return f"{b:02X}"


def compute_information(n, counts):
    pj = [0.0]*256
    Ij = [0.0]*256
    contrib = [0.0]*256
    for j in range(256):
        c = counts[j]
        if c == 0 or n == 0:
            pj[j] = 0.0
            Ij[j] = 0.0
            contrib[j] = 0.0
        else:
            p = c / n
            pj[j] = p
            I = -math.log2(p)
            Ij[j] = I
            contrib[j] = c * I
    I_total_bits = sum(contrib)
    return pj, Ij, contrib, I_total_bits


def make_report(path, n, counts, pj, Ij, contrib, I_bits, outpath):
    now = datetime.now().isoformat(sep=' ', timespec='seconds')
    with open(outpath, 'w', encoding='utf-8') as r:
        r.write(f"Отчёт: анализ файла {path}\nДата: {now}\n\n")
        r.write(f"Длина файла n = {n} байт\n")
        L_bits = n * 8
        r.write(f"L(Q) = n * 8 = {L_bits} бит\n")
        r.write('\n')
        r.write(f"I_BP(Q) = суммарная информация (бит) = {I_bits:.2f}\n")
        frac = I_bits - math.floor(I_bits)
        r.write(f"Дробная часть {{I_BP(Q)}} = {frac:.2e}\n")
        r.write('\n')
        I_octets = I_bits / 8.0
        r.write(f"Длина в октетах L(Q) = n = {n} октетов\n")
        r.write(f"I_BP(Q) (октеты) = {I_octets:.2f}\n")
        E = math.ceil(I_octets)
        G64 = E + 256 * 8
        G8 = E + 256 * 1
        r.write(f"E (нижняя оценка, октетов) = ceil(I_BP(Q)_octets) = {E}\n")
        r.write(f"G64 (E + 256*8) = {G64} октетов\n")
        r.write(f"G8  (E + 256*1) = {G8} октетов\n")
        r.write('\n')
        r.write('Таблица по байту (00..FF):\n')
        r.write('hex\tcount\tp(j)\tI(j)[бит]\tcontrib=count*I(j)[бит]\n')
        for j in range(256):
            r.write(f"{format_hex(j)}\t{counts[j]}\t{pj[j]:.6f}\t{Ij[j]:.6f}\t{contrib[j]:.6f}\n")
        r.write('\n')
        r.write('Таблица по убыванию count:\n')
        r.write('rank\thex\tcount\tp(j)\tI(j)[бит]\tcontrib=count*I(j)[бит]\n')
        sorted_by_count = sorted(range(256), key=lambda x: counts[x], reverse=True)
        for rank, j in enumerate(sorted_by_count, start=1):
            r.write(f"{rank}\t{format_hex(j)}\t{counts[j]}\t{pj[j]:.6f}\t{Ij[j]:.6f}\t{contrib[j]:.6f}\n")
    print(f"Отчёт сохранён в {outpath}")


def print_summary(n, I_bits, counts):
    L_bits = n * 8
    print(f"Длина файла: n = {n} байт, L(Q) = {L_bits} бит")
    print(f"I_BP(Q) = {I_bits:.2f} бит")
    frac = I_bits - math.floor(I_bits)
    print(f"Дробная часть {{I_BP(Q)}} = {frac:.2e}")
    I_octets = I_bits / 8.0
    print(f"L(Q) = {n} октетов; I_BP(Q) = {I_octets:.2f} октетов")
    E = math.ceil(I_octets)
    G64 = E + 256*8
    G8 = E + 256*1
    print(f"E = {E} октетов; G64 = {G64} октетов; G8 = {G8} октетов")


def make_tests():
    # Текстовый файл
    with open('test_text.txt', 'w', encoding='utf-8') as f:
        f.write("Привет мир! Это тестовый текстовый файл.\n")
    # Бинарный файл с равномерным распределением (00..FF повтор)
    with open('test_bin.bin', 'wb') as f:
        f.write(bytes(range(256)) * 4)  # 1024 байта
    # Монотонный файл
    with open('test_repeated.bin', 'wb') as f:
        f.write(b'\xAA' * 1024)
    # Маленький контрольный файл a,b,c,d
    with open('test_small.bin', 'wb') as f:
        f.write(b'\x01\x02\x03\x04')
    print("Тестовые файлы созданы: test_text.txt, test_bin.bin, test_repeated.bin, test_small.bin")


def main():
    ap = argparse.ArgumentParser(description='Byte-wise entropy / information analyser')
    ap.add_argument('file', nargs='?', help='input file to analyze')
    ap.add_argument('-o', '--output', default='report.txt', help='report file (text)')
    ap.add_argument('--no-report', action='store_true', help='do not write report, only print summary')
    ap.add_argument('--make-tests', action='store_true', help='create test files and exit')
    args = ap.parse_args()

    if args.make_tests:
        make_tests()
        return

    if not args.file:
        print("Укажите файл для анализа или --make-tests для создания тестов.")
        sys.exit(1)

    n, counts = analyze_file(args.file)
    pj, Ij, contrib, I_bits = compute_information(n, counts)
    print_summary(n, I_bits, counts)
    if not args.no_report:
        make_report(args.file, n, counts, pj, Ij, contrib, I_bits, args.output)


if __name__ == '__main__':
    main()
