#!/usr/bin/env python3
"""
Универсальный декодер формата L3ARCH (версии 0, 1, 2).
ЛР4.№3
"""
#python3 universal_decoder.py <архив> -d <папка_для_распаковки>
import struct
import sys
from pathlib import Path
from binascii import crc32
import zlib
import argparse
from collections import Counter
import heapq



# ==============================
# === Общие константы формата ===
# ==============================

SIGNATURE_PREFIX = b'L3ARCH'   # обязательные первые 6 байт
ALG_PROT_CRC32 = 11            # код CRC32

# ==============================
# === Реализация Хаффмана (нужна для версии 2) ===
# ==============================

class HNode:
    """Узел дерева Хаффмана"""
    def __init__(self, freq, symbol=None, left=None, right=None):
        self.freq = freq
        self.symbol = symbol
        self.left = left
        self.right = right

    def __lt__(self, other):
        """Сравнение узлов для очереди с приоритетом"""
        if self.freq == other.freq:
            return (self.symbol or 0) < (other.symbol or 0)
        return self.freq < other.freq

def build_huffman_tree(freqs):
    """Строим дерево Хаффмана по словарю {символ: частота}"""
    heap = [HNode(fr, sym) for sym, fr in freqs.items()]
    heapq.heapify(heap)
    if len(heap) == 0:
        return None
    if len(heap) == 1:
        # крайний случай: в файле только один символ
        only = heap[0]
        return HNode(only.freq, None, only, None)
    while len(heap) > 1:
        a = heapq.heappop(heap)
        b = heapq.heappop(heap)
        heapq.heappush(heap, HNode(a.freq + b.freq, None, a, b))
    return heap[0]

def huffman_decode_bytes(encoded_bytes, service_bytes, orig_size):
    """
    Декодирование Хаффмана.
    service_bytes хранит:
      - padding (uint16) — сколько бит добавлено до байта
      - num_symbols (uint16) — число различных символов
      - список (uint8 символ, uint32 частота)
    """
    if len(service_bytes) < 4:
        return b''

    # читаем padding и число символов
    padding, = struct.unpack_from("<H", service_bytes, 0)
    num_syms, = struct.unpack_from("<H", service_bytes, 2)

    # читаем таблицу частот
    freqs = {}
    off = 4
    for _ in range(num_syms):
        sym, fr = struct.unpack_from("<BI", service_bytes, off)
        off += 5
        freqs[sym] = fr

    # восстанавливаем дерево
    root = build_huffman_tree(freqs)
    if root is None:
        return b''

    # преобразуем байты в битовую строку
    bitstr = bin(int.from_bytes(encoded_bytes, 'big'))[2:].zfill(len(encoded_bytes) * 8)
    if padding:
        bitstr = bitstr[:-padding]

    # декодируем
    out = bytearray()
    node = root
    for bit in bitstr:
        node = node.left if bit == '0' else node.right
        if node.symbol is not None:
            out.append(node.symbol)
            node = root
            if len(out) >= orig_size:
                break
    return bytes(out[:orig_size])

# ==============================
# === Декодер версии 0 (Л3.№1) ===
# ==============================

def decode_v0(archive_path: Path, outdir: Path):
    """
    Формат v0 (Л3.№1):
      - 6 байт сигнатура "L3ARCH"
      - 2 байта версия (uint16)
      - 8 байт длина исходного файла
      - далее байты исходного файла
    """
    with archive_path.open('rb') as f:
        # пропускаем уже проверенные 8 байт
        f.seek(8)
        
        # Читаем длину исходного файла
        orig_len = struct.unpack('<Q', f.read(8))[0]
        
        # Читаем данные
        data = f.read(orig_len)
        
        # Проверяем, что прочитали достаточно данных
        if len(data) != orig_len:
            raise ValueError(f"v0: ожидалось {orig_len} байт, получено {len(data)}")

    # сохраняем восстановленный файл
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "restored_v0.bin"
    with outfile.open('wb') as o:
        o.write(data)
    print(f"[v0] Восстановлен {outfile} ({len(data)} байт)")

# ==============================
# === Декодер версии 1 (Л3.№2) ===
# ==============================

def decode_v1(archive_path: Path, outdir: Path):
    """
    Формат v1 (Л3.№2):
    Заголовок:
      - 8 байт сигнатура
      - 2 байта версия
      - 1 байт alg_ctx
      - 1 байт alg_noctx (0=none, 2=zlib)
      - 1 байт alg_prot (0=none, 11=CRC32)
      - 1 байт reserved
      - 8 байт header_size
      - 4 байта num_entries
    Затем таблица записей и данные файлов.
    """
    with archive_path.open('rb') as f:
        sig = f.read(8)
        if sig[:6] != SIGNATURE_PREFIX:
            raise ValueError("v1: неверная сигнатура")
        version = struct.unpack('<H', f.read(2))[0]
        alg_ctx = f.read(1)[0]
        alg_noctx = f.read(1)[0]
        alg_prot = f.read(1)[0]
        _ = f.read(1)
        header_size = struct.unpack('<Q', f.read(8))[0]
        num_entries = struct.unpack('<I', f.read(4))[0]

        # читаем записи
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

        outdir.mkdir(parents=True, exist_ok=True)
        # читаем данные
        for entry_type, relpath, orig_size, stored_size, service in entries_meta:
            target = outdir / Path(relpath)
            target.parent.mkdir(parents=True, exist_ok=True)
            stored_bytes = f.read(stored_size) if stored_size else b''

            # проверка CRC
            expected_crc = None
            if alg_prot == ALG_PROT_CRC32 and len(service) >= 4:
                expected_crc = struct.unpack('<I', service[:4])[0]

            # декодирование
            if alg_noctx == 2:
                raw = zlib.decompress(stored_bytes)
            else:
                raw = stored_bytes

            # проверка CRC
            if expected_crc is not None:
                actual_crc = crc32(raw) & 0xffffffff
                if actual_crc != expected_crc:
                    print(f"[v1] CRC ошибка для {relpath}")

            with target.open('wb') as o:
                o.write(raw)
            print(f"[v1] Восстановлен: {relpath}")

# ==============================
# === Декодер версии 2 (Л4.№1) ===
# ==============================

def decode_v2(archive_path: Path, outdir: Path):
    """
    Формат v2 (Л4.№1):
    Поддерживает Хаффман (alg_noctx=3) и CRC32.
    """
    with archive_path.open('rb') as f:
        sig = f.read(8)
        if sig[:6] != SIGNATURE_PREFIX:
            raise ValueError("v2: неверная сигнатура")
        version = struct.unpack('<H', f.read(2))[0]
        alg_ctx = f.read(1)[0]
        alg_noctx = f.read(1)[0]
        alg_prot = f.read(1)[0]
        _ = f.read(1)
        header_size = struct.unpack('<Q', f.read(8))[0]
        num_entries = struct.unpack('<I', f.read(4))[0]

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

        outdir.mkdir(parents=True, exist_ok=True)
        for entry_type, relpath, orig_size, stored_size, service in entries_meta:
            target = outdir / Path(relpath)
            target.parent.mkdir(parents=True, exist_ok=True)
            stored_bytes = f.read(stored_size) if stored_size else b''

            # Хаффман
            if alg_noctx == 3:
                crc_val = None
                if alg_prot == ALG_PROT_CRC32 and len(service) >= 4:
                    crc_val = struct.unpack('<I', service[-4:])[0]
                    service = service[:-4]
                raw = huffman_decode_bytes(stored_bytes, service, orig_size)
                if crc_val is not None and (crc32(raw) & 0xffffffff) != crc_val:
                    print(f"[v2] CRC ошибка для {relpath}")
            elif alg_noctx == 2:
                raw = zlib.decompress(stored_bytes)
            else:
                raw = stored_bytes

            with target.open('wb') as o:
                o.write(raw)
            print(f"[v2] Восстановлен: {relpath}")


    
    
    
def decode_v3(archive_path: Path, outdir: Path):
    """
    Формат v3 (интеллектуальный кодер Л4.№4):
    - Для каждого файла в service первый байт - код алгоритма
    - Остальная часть service - мета-информация алгоритма
    """
    with archive_path.open('rb') as f:
        sig = f.read(8)
        if sig[:6] != b'L3ARCH':
            raise ValueError("v3: неверная сигнатура")
        
        version = struct.unpack('<H', f.read(2))[0]
        alg_ctx = f.read(1)[0]
        alg_noctx = f.read(1)[0]  # не используется в v3
        alg_prot = f.read(1)[0]
        _ = f.read(1)
        header_size = struct.unpack('<Q', f.read(8))[0]
        num_entries = struct.unpack('<I', f.read(4))[0]

        # Чтение метаданных записей
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

        outdir.mkdir(parents=True, exist_ok=True)

        # Обработка файлов
        for entry_type, relpath, orig_size, stored_size, service in entries_meta:
            target = outdir / Path(relpath)
            target.parent.mkdir(parents=True, exist_ok=True)
            stored_bytes = f.read(stored_size) if stored_size else b''

            if entry_type == 1:  # ENTRY_FILE
                # Извлекаем код алгоритма из service
                algorithm_code = service[0] if service else 0
                meta_info = service[1:] if service else b''
                
                # Декодирование в зависимости от алгоритма
                if algorithm_code == 0:
                    # Без сжатия
                    raw_data = stored_bytes
                elif algorithm_code == 3:
                    # Хаффман
                    raw_data = huffman_decode(stored_bytes, meta_info, orig_size)
                else:
                    raise ValueError(f"Неизвестный код алгоритма: {algorithm_code}")
                
                # Проверка CRC если включена
                if alg_prot == 11 and len(meta_info) >= 4:
                    crc_val = struct.unpack('<I', meta_info[-4:])[0]
                    actual_crc = crc32(raw_data) & 0xffffffff
                    if actual_crc != crc_val:
                        print(f"[v3] Ошибка CRC для {relpath}")

                with target.open('wb') as o:
                    o.write(raw_data)
                print(f"[v3] Восстановлен: {relpath}")

# ==============================
# === Диспетчер версий ===
# ==============================

def universal_decode(archive_path: Path, outdir: Path):
    with archive_path.open('rb') as f:
        head = f.read(8)
        if head[:6] != b'L3ARCH':
            raise ValueError("Ошибка: неверная сигнатура")
        
        # получаем версию из уже прочитанных байтов
        version = struct.unpack('<H', head[6:8])[0]

    print(f"Сигнатура верна, версия {version}")

    if version == 0:
        decode_v0(archive_path, outdir)
    elif version == 1:
        decode_v1(archive_path, outdir)
    elif version == 2:
        decode_v2(archive_path, outdir)
    elif version == 3:
        decode_v3(archive_path, outdir)
    else:
        raise RuntimeError(f"Неизвестная версия формата: {version}")


# ==============================
# === CLI ===
# ==============================

def main():
    parser = argparse.ArgumentParser(description="Универсальный декодер L3ARCH (версии 0,1,2)")
    parser.add_argument("archive", help="Путь к архиву")
    parser.add_argument("-d", "--outdir", default=".", help="Каталог для распаковки")
    args = parser.parse_args()

    archive_path = Path(args.archive)
    outdir = Path(args.outdir)

    if not archive_path.exists():
        print("Файл архива не найден")
        sys.exit(2)

    try:
        universal_decode(archive_path, outdir)
        print("Распаковка завершена")
    except Exception as e:
        print("Ошибка:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
