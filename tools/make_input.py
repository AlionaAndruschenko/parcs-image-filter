#!/usr/bin/env python3
"""Конвертує звичайне зображення (jpg/png) у input.txt для PARCS.

Приклад:
  python3 tools/make_input.py photo.jpg input.txt --filter gauss --size 7 --sigma 2.0 --width 800
  python3 tools/make_input.py photo.jpg input_w2.txt --workers 2      # лише 2 воркери
  python3 tools/make_input.py photo.jpg input_seq.txt --mode seq      # послідовний варіант
Потрібно: pip install pillow
"""
import argparse
from PIL import Image


def main():
    p = argparse.ArgumentParser()
    p.add_argument('image')
    p.add_argument('output')
    p.add_argument('--filter', default='gauss', choices=['gauss', 'box'])
    p.add_argument('--size', type=int, default=7, help='розмір ядра (непарне)')
    p.add_argument('--sigma', type=float, default=2.0)
    p.add_argument('--workers', type=int, default=0, help='0 = всі увімкнені воркери')
    p.add_argument('--mode', default='par', choices=['par', 'seq'])
    p.add_argument('--width', type=int, default=0, help='зменшити до цієї ширини (0 = як є)')
    p.add_argument('--gray', action='store_true', help='сіре зображення (P2) замість кольорового')
    a = p.parse_args()

    img = Image.open(a.image).convert('L' if a.gray else 'RGB')
    if a.width and img.width > a.width:
        img = img.resize((a.width, round(img.height * a.width / img.width)), Image.LANCZOS)

    data = img.tobytes()
    ch = 1 if a.gray else 3
    row_len = img.width * ch
    with open(a.output, 'w') as f:
        f.write('filter=%s size=%d sigma=%s workers=%d mode=%s\n'
                % (a.filter, a.size, a.sigma, a.workers, a.mode))
        f.write('P2\n' if a.gray else 'P3\n')
        f.write('%d %d\n255\n' % (img.width, img.height))
        for y in range(img.height):
            f.write(' '.join(map(str, data[y * row_len:(y + 1) * row_len])))
            f.write('\n')
    print('Saved %s: %dx%d, %s' % (a.output, img.width, img.height, 'P2' if a.gray else 'P3'))


if __name__ == '__main__':
    main()
