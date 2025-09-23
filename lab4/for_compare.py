import math
from collections import Counter
import os

def entropy_analysis(path):
    with open(path, "rb") as f:
        data = f.read()
    n = len(data)
    freqs = Counter(data)
    probs = [c/n for c in freqs.values()]
    H = -sum(p * math.log2(p) for p in probs)
    I = H * n
    print(f"Файл: {path}")
    print(f"Размер: {n} байт")
    print(f"Энтропия: {H:.4f} бит/символ")
    print(f"Количество информации: {I:.2f} бит ({I/8:.2f} байт)")
    return I

# пример использования
I = entropy_analysis("test_text.txt")

# после архивирования можно сравнить:
archive_size = os.path.getsize("archive.l3")
print(f"Размер архива: {archive_size} байт")