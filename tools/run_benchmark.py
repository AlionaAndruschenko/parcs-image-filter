#!/usr/bin/env python3
"""Автоматично запускає задачу на PARCS для N = 1..K воркерів (+ послідовний варіант),
чекає завершення, завантажує output, збирає час у results.csv.

Приклад:
  python3 tools/run_benchmark.py --master http://MASTER_IP:8080 --image samples/test_image.png \
      --max-workers 4 --size 7 --sigma 2.0 --repeats 3
Потрібно: pip install pillow requests
"""
import argparse
import csv
import os
import re
import statistics
import subprocess
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def last_job_id(master):
    html = requests.get(master + '/jobs', timeout=30).text
    ids = [int(x) for x in re.findall(r'data-job-id="(\d+)"', html)]
    return max(ids) if ids else -1


def submit(master, name, solution, input_file):
    before = last_job_id(master)
    with open(solution, 'rb') as s, open(input_file, 'rb') as i:
        r = requests.post(master + '/api/job', data={'job_name': name},
                          files={'solution_file': s, 'input_file': i}, timeout=600)
    r.raise_for_status()
    # id нової задачі = наступний після останнього
    for _ in range(30):
        jid = last_job_id(master)
        if jid > before:
            return jid
        time.sleep(1)
    raise RuntimeError('job id not found')


def wait_output(master, jid, out_path, timeout=3600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = requests.get('%s/api/job/%d/output' % (master, jid), timeout=600)
        if r.status_code == 200:
            with open(out_path, 'wb') as f:
                f.write(r.content)
            return
        html = requests.get(master + '/jobs', timeout=30).text
        block = html.split('data-job-id="%d"' % jid, 1)[-1][:600]
        if 'reason:' in block:
            raise RuntimeError('job %d failed: %s' % (jid, re.sub(r'\s+', ' ', block[:300])))
        time.sleep(2)
    raise TimeoutError('job %d timeout' % jid)


def parse_times(path):
    t = {}
    with open(path) as f:
        for line in f:
            if not line.startswith('#'):
                if t.get('time_total') is not None:
                    break
                continue
            m = re.match(r'#\s*(time_\w+)=([\d.]+)', line)
            if m:
                t[m.group(1)] = float(m.group(2))
    return t


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--master', required=True)
    p.add_argument('--image', default=os.path.join(ROOT, 'samples', 'test_image.png'))
    p.add_argument('--max-workers', type=int, default=4)
    p.add_argument('--filter', default='gauss')
    p.add_argument('--size', type=int, default=7)
    p.add_argument('--sigma', type=float, default=2.0)
    p.add_argument('--width', type=int, default=0)
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--no-seq', action='store_true', help='не запускати послідовний варіант')
    p.add_argument('--out-dir', default=os.path.join(ROOT, 'results'))
    a = p.parse_args()
    master = a.master.rstrip('/')
    os.makedirs(a.out_dir, exist_ok=True)

    runs = ([('seq', 0)] if not a.no_seq else []) + [('par', n) for n in range(1, a.max_workers + 1)]
    rows = []
    for mode, n in runs:
        inp = os.path.join(a.out_dir, 'input_%s_%d.txt' % (mode, n))
        subprocess.check_call([sys.executable, os.path.join(HERE, 'make_input.py'), a.image, inp,
                               '--filter', a.filter, '--size', str(a.size), '--sigma', str(a.sigma),
                               '--workers', str(n), '--mode', mode, '--width', str(a.width)])
        comp, total = [], []
        for rep in range(a.repeats):
            name = 'blur_%s_N%d_run%d' % (mode, n, rep + 1)
            jid = submit(master, name, os.path.join(ROOT, 'solver.py'), inp)
            out = os.path.join(a.out_dir, 'output_%s_%d_run%d.txt' % (mode, n, rep + 1))
            wait_output(master, jid, out)
            t = parse_times(out)
            comp.append(t['time_compute'])
            total.append(t['time_total'])
            print('%-22s job #%d  compute=%.3f s  total=%.3f s' % (name, jid, comp[-1], total[-1]))
        rows.append({'mode': mode, 'workers': n,
                     'compute_s': round(statistics.median(comp), 3),
                     'total_s': round(statistics.median(total), 3)})

    # прискорення відносно N=1
    base = next((r['compute_s'] for r in rows if r['mode'] == 'par' and r['workers'] == 1), None)
    for r in rows:
        r['speedup'] = round(base / r['compute_s'], 2) if base else ''
    csv_path = os.path.join(a.out_dir, 'results.csv')
    with open(csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['mode', 'workers', 'compute_s', 'total_s', 'speedup'])
        w.writeheader()
        w.writerows(rows)
    print('Saved', csv_path)
    # картинка-результат з останнього запуску
    subprocess.call([sys.executable, os.path.join(HERE, 'decode_output.py'), out,
                     os.path.join(a.out_dir, 'result.png')])


if __name__ == '__main__':
    main()
