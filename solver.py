# -*- coding: utf-8 -*-
"""
PARCS-Python: паралельна фільтрація зображень (2D-конволюція).

Фільтри:
  box   - розмиття (усереднення по вікну k x k)
  gauss - Гауссів фільтр (ядро k x k, параметр sigma)

Ідея розпаралелювання (data decomposition):
  1. Master читає зображення і ділить його на N горизонтальних смуг (по рядках),
     де N - кількість воркерів.
  2. Кожна смуга відправляється воркеру разом з "гало" (halo) - r = k // 2
     додатковими рядками зверху та знизу, бо для пікселя на краю смуги
     потрібні сусіди з сусідньої смуги.
  3. Воркери паралельно рахують конволюцію своєї смуги і повертають результат.
  4. Master склеює смуги в одне зображення (reduce) і записує вихід.

Формат input.txt:
  1-й рядок - параметри, напр.:  filter=gauss size=7 sigma=2.0 workers=0 mode=par
      workers=0  -> використати всіх увімкнених воркерів, workers=K -> лише перших K
      mode=seq   -> послідовний варіант (усе рахує master, для порівняння)
  далі - зображення у текстовому форматі PPM (P3, кольорове) або PGM (P2, сіре).
Вихід output.txt - те саме зображення (P3/P2) після фільтрації; у коментарях (#)
записано статистику часу.

Код сумісний з Python 2.7 (на ньому працює PARCS-Python) і з Python 3.
"""
from Pyro4 import expose
import base64
import math
import socket
import time


def _value(r):
    """Pyro4-проксі в PARCS асинхронні: виклик повертає FutureResult (.value).
    Якщо раптом проксі синхронний - повертаємо результат як є."""
    return r.value if hasattr(r, 'value') else r


class Solver:
    def __init__(self, workers=None, input_file_name=None, output_file_name=None):
        self.input_file_name = input_file_name
        self.output_file_name = output_file_name
        self.workers = workers if workers is not None else []

    # ------------------------------------------------------------------ master
    def solve(self):
        t_start = time.time()
        params, img = self.read_input()
        t_read = time.time()

        width, height, channels, maxval, pixels = img
        size = int(params.get('size', 5))
        if size % 2 == 0:
            size += 1                      # ядро має бути непарного розміру
        kernel = Solver.make_kernel(params.get('filter', 'gauss'), size,
                                    float(params.get('sigma', size / 3.0)))
        mode = params.get('mode', 'par')

        workers = list(self.workers)
        limit = int(params.get('workers', 0))
        if limit > 0:
            workers = workers[:limit]
        n = len(workers) if mode == 'par' else 0
        print("Job started: %dx%d, channels=%d, kernel=%dx%d, workers=%d"
              % (width, height, channels, size, size, n))

        t_comp_start = time.time()
        if n == 0:
            # послідовний варіант: master рахує все сам
            res = Solver.convolve_strip(Solver.encode(pixels), width, channels,
                                        kernel, size, 0, height)
            out_bytes = Solver.decode(res[0])
            stats = [(socket.gethostname(), 0, height, res[1])]
        else:
            out_bytes, stats = self.run_parallel(workers, pixels, width, height,
                                                 channels, kernel, size)
        t_comp_end = time.time()

        self.write_output(img, out_bytes, params, n, stats,
                          t_read - t_start, t_comp_end - t_comp_start,
                          time.time() - t_start)
        print("Job finished: compute %.3f s" % (t_comp_end - t_comp_start))

    def run_parallel(self, workers, pixels, width, height, channels, kernel, size):
        n = len(workers)
        r = size // 2
        row_len = width * channels
        # ділимо рядки максимально рівномірно
        bounds = []
        base, extra = divmod(height, n)
        y = 0
        for i in range(n):
            h = base + (1 if i < extra else 0)
            bounds.append((y, y + h))
            y += h

        # map: відправляємо кожному воркеру його смугу + гало
        futures = []
        for i, (y0, y1) in enumerate(bounds):
            s0 = max(0, y0 - r)
            s1 = min(height, y1 + r)
            strip = pixels[s0 * row_len: s1 * row_len]
            futures.append(workers[i].convolve_strip(
                Solver.encode(strip), width, channels, kernel, size, y0 - s0, y1 - y0))

        # reduce: збираємо результати в правильному порядку
        parts = []
        stats = []
        for i, f in enumerate(futures):
            res = _value(f)
            parts.append(Solver.decode(res[0]))
            stats.append((res[2], bounds[i][0], bounds[i][1], res[1]))
        out = bytearray()
        for p in parts:
            out.extend(p)
        return out, stats

    # ------------------------------------------------------------------ worker
    @staticmethod
    @expose
    def convolve_strip(data_b64, width, channels, kernel, size, pad_top, out_rows):
        """Конволюція однієї смуги.
        data_b64 - смуга (разом з гало) як base64 від байтів пікселів;
        pad_top  - скільки рядків гало зверху; out_rows - скільки рядків порахувати.
        Повертає (base64 результату, час обчислення, ім'я хоста)."""
        t0 = time.time()
        width = int(width)
        channels = int(channels)
        size = int(size)
        pad_top = int(pad_top)
        out_rows = int(out_rows)
        data = Solver.decode(data_b64)
        r = size // 2
        row_len = width * channels
        in_rows = len(data) // row_len

        # розбиваємо на окремі канали; кожен рядок доповнюємо r пікселями
        # зліва/справа копією крайнього (обробка межі "replicate")
        planes = []
        for c in range(channels):
            rows = []
            for y in range(in_rows):
                row = list(data[y * row_len + c: (y + 1) * row_len: channels])
                rows.append([row[0]] * r + row + [row[-1]] * r)
            planes.append(rows)

        out = bytearray(out_rows * row_len)
        xr = range(width)
        for c in range(channels):
            rows = planes[c]
            for oy in range(out_rows):
                cy = pad_top + oy                 # центр у координатах смуги
                acc = [0.0] * width
                for ky in range(size):
                    sy = cy + ky - r
                    if sy < 0:
                        sy = 0                    # верхня межа зображення
                    elif sy >= in_rows:
                        sy = in_rows - 1          # нижня межа зображення
                    src = rows[sy]
                    krow = kernel[ky * size:(ky + 1) * size]
                    for kx in range(size):
                        w = krow[kx]
                        seg = src[kx:kx + width]
                        acc = [a + w * v for a, v in zip(acc, seg)]
                base_i = oy * row_len + c
                for x in xr:
                    v = int(acc[x] + 0.5)
                    out[base_i + x * channels] = 255 if v > 255 else (0 if v < 0 else v)

        return Solver.encode(out), time.time() - t0, socket.gethostname()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    @expose
    def make_kernel(kind, size, sigma):
        r = size // 2
        if kind == 'box':
            k = [1.0] * (size * size)
        else:
            k = []
            for y in range(-r, r + 1):
                for x in range(-r, r + 1):
                    k.append(math.exp(-(x * x + y * y) / (2.0 * sigma * sigma)))
        s = sum(k)
        return [v / s for v in k]

    @staticmethod
    def encode(b):
        s = base64.b64encode(bytes(b))
        return s.decode('ascii') if not isinstance(s, str) else s

    @staticmethod
    def decode(s):
        if not isinstance(s, bytes):
            s = s.encode('ascii')
        return bytearray(base64.b64decode(s))

    def read_input(self):
        f = open(self.input_file_name, 'r')
        params = {}
        tokens = []
        first = True
        for line in f:
            if first:
                first = False
                for item in line.split():
                    if '=' in item:
                        k, v = item.split('=', 1)
                        params[k.strip().lower()] = v.strip()
                continue
            line = line.split('#', 1)[0]
            tokens.extend(line.split())
        f.close()

        magic = tokens[0]
        channels = 3 if magic == 'P3' else 1
        if magic not in ('P2', 'P3'):
            raise ValueError("Expected PPM P3 or PGM P2, got %s" % magic)
        width, height, maxval = int(tokens[1]), int(tokens[2]), int(tokens[3])
        need = width * height * channels
        vals = tokens[4:4 + need]
        if len(vals) != need:
            raise ValueError("Expected %d pixel values, got %d" % (need, len(vals)))
        if maxval == 255:
            pixels = bytearray(int(v) for v in vals)
        else:
            pixels = bytearray(int(int(v) * 255.0 / maxval + 0.5) for v in vals)
        return params, (width, height, channels, 255, pixels)

    def write_output(self, img, out_bytes, params, n, stats, t_read, t_comp, t_total):
        width, height, channels, maxval, _ = img
        f = open(self.output_file_name, 'w')
        f.write('P3\n' if channels == 3 else 'P2\n')
        f.write('# PARCS image filter: %s\n' % ' '.join(
            '%s=%s' % (k, params[k]) for k in sorted(params)))
        f.write('# workers=%d\n' % n)
        f.write('# time_read=%.3f\n' % t_read)
        f.write('# time_compute=%.3f\n' % t_comp)
        f.write('# time_total=%.3f\n' % t_total)
        for host, y0, y1, t in stats:
            f.write('# worker %s rows %d-%d compute %.3f s\n' % (host, y0, y1 - 1, t))
        f.write('%d %d\n%d\n' % (width, height, maxval))
        per_line = width * channels
        for y in range(height):
            row = out_bytes[y * per_line:(y + 1) * per_line]
            f.write(' '.join(str(v) for v in row))
            f.write('\n')
        f.close()
