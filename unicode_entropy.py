#!/usr/bin/env python3
import math
import argparse
from collections import Counter
import os

# === Вспомогательные функции ===

def compute_entropy_and_lengths(text, encoding="UTF-32"):
    """
    Вычисляет характеристики текста:
    - энтропию
    - суммарное количество информации
    - размер метаданных
    - нижнюю границу длины архива
    Также формирует таблицу символов: (символ, код, частота, вероятность, информация).
    """

    # 1. Общая длина текста
    n = len(text)

    # 2. Частоты появления каждого символа
    freqs = Counter(text)

    # 3. Вероятности появления символов
    probs = {ch: count / n for ch, count in freqs.items()}

    # 4. Энтропия источника
    entropy = -sum(p * math.log2(p) for p in probs.values())

    # 5. Суммарное количество информации (бит)
    total_info_bits = n * entropy

    # 6. Мощность алфавита
    alphabet_size = len(freqs)

    # 7. Метаданные: 64-битная длина текста
    meta_size = 8

    # 8. Размер записи одного символа (в зависимости от выбранной кодировки)
    if encoding == "UTF-8":
        meta_size += sum(len(ch.encode("utf-8")) + 8 for ch in freqs)
    elif encoding == "UTF-16":
        meta_size += alphabet_size * (2 + 8)
    else:  # UTF-32
        meta_size += alphabet_size * (4 + 8)

    # 9. Нижняя граница длины архива (бит → округляем вверх до байт)
    archive_lower_bound_bits = total_info_bits + meta_size * 8
    archive_lower_bound_bytes = math.ceil(archive_lower_bound_bits / 8)

    # 10. Сравнение: если бы сохраняли все частоты для всего Unicode
    full_unicode_size = 1114112 * 8  # 8 байт * 1,114,112 символов

    # 11. Таблица символов
    table = []
    for ch, count in freqs.items():
        p = probs[ch]
        info = -math.log2(p)
        table.append((ch, ord(ch), count, p, info))

    return {
        "n": n,
        "alphabet_size": alphabet_size,
        "entropy": entropy,
        "total_info_bits": total_info_bits,
        "meta_size_bytes": meta_size,
        "archive_lower_bound_bytes": archive_lower_bound_bytes,
        "full_unicode_size_bytes": full_unicode_size,
        "table": table
    }


def format_report(results):
    """
    Формирует развернутый текстовый отчёт для печати и сохранения.
    """

    lines = []
    lines.append("\n=== Итоговый отчёт ===")
    lines.append(f"Длина текста (символы): {results['n']}")
    lines.append(f"Мощность алфавита A1: {results['alphabet_size']}")
    lines.append(f"Энтропия H(Q): {results['entropy']:.4f} бит/символ")
    lines.append(f"Суммарное количество информации: {results['total_info_bits']:.2f} бит")
    lines.append(f"Размер метаданных: {results['meta_size_bytes']} байт")
    lines.append(f"Оценка снизу длины архива: {results['archive_lower_bound_bytes']} байт")
    lines.append(f"Если бы сохраняли частоты для всего Unicode: "
                 f"{results['full_unicode_size_bytes']/1024/1024:.2f} МБ\n")

    # === Таблица по алфавиту ===
    lines.append("=== Таблица (по алфавиту) ===")
    lines.append(f"{'Символ':^8} {'Код':^6} {'Count':^10} {'p(j)':^12} {'I(j), бит':^12}")
    for ch, code, count, p, info in sorted(results["table"], key=lambda x: x[1]):
        symbol = ch if ch.isprintable() else f"U+{code:04X}"
        lines.append(f"{symbol:^8} {code:^6} {count:^10} {p:^12.6f} {info:^12.4f}")

    # === Таблица по убыванию частот ===
    lines.append("\n=== Таблица (по убыванию частот) ===")
    lines.append(f"{'Символ':^8} {'Код':^6} {'Count':^10} {'p(j)':^12} {'I(j), бит':^12}")
    for ch, code, count, p, info in sorted(results["table"], key=lambda x: x[2], reverse=True):
        symbol = ch if ch.isprintable() else f"U+{code:04X}"
        lines.append(f"{symbol:^8} {code:^6} {count:^10} {p:^12.6f} {info:^12.4f}")

    return "\n".join(lines)


def save_report(report_text, filename="report_unicode.txt"):
    """Сохраняет отчёт в текстовый файл."""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n✅ Отчёт сохранён в {filename}")


# === Генерация тестовых файлов ===
def generate_test_files():
    #python3 unicode_entropy.py dummy --gen-tests
    #python3 unicode_entropy.py test_files/mixed.txt --encoding UTF-32 --save
    """
    Создает несколько тестовых файлов:
    1. text.txt – простой текст
    2. binary.bin – бинарные данные
    3. mixed.txt – текст с Unicode-символами
    """
    os.makedirs("test_files", exist_ok=True)

    with open("text.txt", "w", encoding="utf-8") as f:
        f.write("hello hello entropy test\n")

    with open("test_files/mixed.txt", "w", encoding="utf-8") as f:
        f.write("Привет 🌍! Hello 世界! 12345\n")

    with open("test_files/binary.bin", "wb") as f:
        f.write(os.urandom(64))  # 64 случайных байта

    print("\n📂 Тестовые файлы созданы в папке test_files/")


# === Основная программа ===
def main():
    parser = argparse.ArgumentParser(description="Л2: анализ текста по Unicode-символам")
    parser.add_argument("file", help="Файл в кодировке UTF-8")
    parser.add_argument("--encoding", choices=["UTF-8", "UTF-16", "UTF-32"], default="UTF-32",
                        help="Формат хранения символа в таблице частот")
    parser.add_argument("--save", action="store_true", help="Сохранить отчёт в файл")
    parser.add_argument("--gen-tests", action="store_true", help="Сгенерировать тестовые файлы")
    args = parser.parse_args()

    if args.gen_tests:
        generate_test_files()
        return

    with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    results = compute_entropy_and_lengths(text, args.encoding)
    report_text = format_report(results)

    print(report_text)

    if args.save:
        save_report(report_text)


if __name__ == "__main__":
    main()
