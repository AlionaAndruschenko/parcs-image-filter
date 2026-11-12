#!/usr/bin/env python3
"""Перетворює output.txt з PARCS у PNG і друкує статистику часу.

Приклад:  python3 tools/decode_output.py output.txt result.png
"""
import sys
from PIL import Image


def read_ppm_text(path):
    stats, tokens = [], []
    with open(path) as f:
        for line in f:
            if line.startswith('#'):
                stats.append(line[1:].strip())
                continue
            tokens.extend(line.split())
    magic, w, h = tokens[0], int(tokens[1]), int(tokens[2])
    ch = 3 if magic == 'P3' else 1
    data = bytes(int(v) for v in tokens[4:4 + w * h * ch])
    img = Image.frombytes('RGB' if ch == 3 else 'L', (w, h), data)
    return img, stats


def main():
    img, stats = read_ppm_text(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else 'result.png'
    img.save(out)
    print('\n'.join(stats))
    print('Saved', out)


if __name__ == '__main__':
    main()
