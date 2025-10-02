# intelligent_coder.py
"""
Интеллектуальный кодер для задания Л4.№4
Использует существующие реализации из archiver_huffman.py и universal_decoder.py
"""

import os
import struct
import argparse
from pathlib import Path
from binascii import crc32

# Импортируем функции из существующих модулей
from archiver_huffman import huffman_encode, huffman_decode
from archiver_huffman import ALG_NOCTX_NONE, ALG_NOCTX_HUFFMAN, ALG_PROT_CRC32

def intelligent_encode_file(data, force_algorithm=None, enable_crc=False):
    """
    Интеллектуальное кодирование одного файла
    
    Args:
        data: исходные данные
        force_algorithm: принудительный выбор алгоритма
        enable_crc: включить CRC
    
    Returns:
        (algorithm_code, encoded_data, meta_info, final_size)
    """
    n_original = len(data)
    
    if force_algorithm is not None:
        # Принудительный режим
        if force_algorithm == 0:
            # Без сжатия
            return 0, data, b'', n_original
        elif force_algorithm == 3:
            # Хаффман
            encoded, meta = huffman_encode(data)
            final_size = len(encoded) + len(meta)
            if enable_crc:
                crc_value = crc32(data) & 0xffffffff
                meta += struct.pack('<I', crc_value)
                final_size += 4
            return 3, encoded, meta, final_size
    else:
        # Интеллектуальный режим - анализируем эффективность
        encoded, meta = huffman_encode(data)
        
        # Расчет суммарного объема
        n_compressed_data = len(encoded)
        n_meta = len(meta)
        n_compressed_total = n_compressed_data + n_meta
        
        if enable_crc:
            n_compressed_total += 4
        
        print(f"  Исходный размер: {n_original} байт")
        print(f"  Сжатые данные: {n_compressed_data} байт")
        print(f"  Мета-информация: {n_meta} байт")
        print(f"  Общий размер архива: {n_compressed_total} байт")
        
        # Проверка целесообразности сжатия
        if n_compressed_total >= n_original:
            print("  ⚡ Несжатое хранение выгоднее")
            return 0, data, b'', n_original
        else:
            print("  ✅ Сжатие выгодно")
            final_size = n_compressed_total
            if enable_crc:
                crc_value = crc32(data) & 0xffffffff
                meta += struct.pack('<I', crc_value)
                final_size += 4
            return 3, encoded, meta, final_size

def create_intelligent_archive(input_files, output_file, force_algorithm=None, enable_crc=False):
    """
    Создание интеллектуального архива
    """
    entries = []
    data_blocks = []
    
    print("🔍 Анализ файлов...")
    
    for input_file in input_files:
        input_path = Path(input_file)
        if not input_path.exists():
            print(f"❌ Файл не найден: {input_file}")
            continue
            
        print(f"\n📁 Обработка: {input_path.name}")
        
        # Чтение файла
        with open(input_path, 'rb') as f:
            data = f.read()
        
        # Интеллектуальное кодирование
        algorithm_code, encoded_data, meta_info, final_size = intelligent_encode_file(
            data, force_algorithm, enable_crc
        )
        
        # Сбор информации о файле
        entry = {
            'type': 1,  # ENTRY_FILE
            'relpath': input_path.name,
            'orig_size': len(data),
            'stored_size': len(encoded_data),
            'service': meta_info,
            'algorithm_code': algorithm_code
        }
        
        entries.append(entry)
        data_blocks.append(encoded_data)
        
        # Расчет эффективности
        efficiency = (len(data) - final_size) / len(data) * 100 if len(data) > 0 else 0
        print(f"  Алгоритм: {'Без сжатия' if algorithm_code == 0 else 'Хаффман'}")
        print(f"  Эффективность: {efficiency:+.1f}%")
    
    if not entries:
        print("❌ Нет файлов для архивации")
        return False
    
    # Создание архива
    return save_archive_v3(output_file, entries, data_blocks, enable_crc)

def save_archive_v3(output_path, entries, data_blocks, enable_crc):
    """
    Сохранение архива в формате версии 3 (совместим с универсальным декодером)
    """
    # Сигнатура и заголовок (аналогично archiver_huffman.py)
    signature = b'L3ARCH04'
    version = 3  # Новая версия для интеллектуального кодера
    alg_ctx = 0
    alg_noctx = 0  # Будет переопределено для каждого файла
    alg_prot = ALG_PROT_CRC32 if enable_crc else 0
    reserved = 0
    
    # Сборка таблицы записей
    table_bytes = bytearray()
    for entry in entries:
        relpath_bytes = entry['relpath'].encode('utf-8')
        service_bytes = bytes([entry['algorithm_code']]) + entry['service']  # Добавляем код алгоритма в service
        
        table_bytes += struct.pack('<B', entry['type'])  # тип записи
        table_bytes += struct.pack('<H', len(relpath_bytes))  # длина пути
        table_bytes += relpath_bytes  # путь
        table_bytes += struct.pack('<Q', entry['orig_size'])  # исходный размер
        table_bytes += struct.pack('<Q', entry['stored_size'])  # размер в архиве
        table_bytes += struct.pack('<I', len(service_bytes))  # длина service
        table_bytes += service_bytes  # service данные
    
    # Расчет размера заголовка
    fixed_header_len = 8 + 2 + 1 + 1 + 1 + 1 + 8 + 4  # сигнатура + версия + alg_ctx + alg_noctx + alg_prot + reserved + header_size + num_entries
    header_size = fixed_header_len + len(table_bytes)
    
    # Запись архива
    with open(output_path, 'wb') as f:
        # Заголовок
        f.write(signature)
        f.write(struct.pack('<H', version))
        f.write(struct.pack('<B', alg_ctx))
        f.write(struct.pack('<B', alg_noctx))
        f.write(struct.pack('<B', alg_prot))
        f.write(struct.pack('<B', reserved))
        f.write(struct.pack('<Q', header_size))
        f.write(struct.pack('<I', len(entries)))
        
        # Таблица записей
        f.write(table_bytes)
        
        # Данные
        for data_block in data_blocks:
            f.write(data_block)
    
    return True

def main():
    parser = argparse.ArgumentParser(description='Интеллектуальный кодер Л4.№4')
    parser.add_argument('inputs', nargs='+', help='Входные файлы')
    parser.add_argument('-o', '--output', required=True, help='Выходной архив')
    parser.add_argument('--algorithm', type=int, choices=[0, 3], 
                       help='Принудительный выбор алгоритма: 0-без сжатия, 3-Хаффман')
    parser.add_argument('--crc', action='store_true', help='Включить проверку CRC')
    
    args = parser.parse_args()
    
    print("🎯 Интеллектуальный кодер Л4.№4")
    print("=" * 50)
    
    if args.algorithm is not None:
        print(f"🔧 Принудительный режим: алгоритм {args.algorithm}")
    else:
        print("🔍 Интеллектуальный режим: анализ эффективности")
    
    if args.crc:
        print("🔒 CRC32: включена проверка целостности")
    
    success = create_intelligent_archive(args.inputs, args.output, args.algorithm, args.crc)
    
    if success:
        print(f"\n✅ Архив успешно создан: {args.output}")
        archive_size = os.path.getsize(args.output)
        print(f"📦 Размер архива: {archive_size} байт")
    else:
        print("\n❌ Ошибка при создании архива")

if __name__ == '__main__':
    main()