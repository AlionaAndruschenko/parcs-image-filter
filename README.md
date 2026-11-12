# Паралельна фільтрація зображень на PARCS-Python (Google Cloud)

Лабораторна робота з курсу «Хмарні обчислення», тема 5.1: **паралельна фільтрація зображень (конволюція: розмиття, Гауссів фільтр)**.
Автор: Андрущенко Альона, група ТТП-42, ФКНК КНУ ім. Тараса Шевченка.

## Ідея алгоритму

Фільтр — це 2D-конволюція: кожен вихідний піксель = зважена сума сусідів у вікні k×k.
- **box** (розмиття) — усі ваги однакові, 1/k²;
- **gauss** (Гауссів фільтр) — ваги `exp(-(x²+y²)/(2σ²))`, нормовані до суми 1.

Розпаралелювання — **декомпозиція даних по рядках**:
1. Master читає зображення і ділить його на N горизонтальних смуг (N = кількість воркерів).
2. Кожен воркер отримує свою смугу + **гало** (halo) — `r = k//2` рядків зверху і знизу, бо пікселям на краю смуги потрібні сусіди з інших смуг.
3. Воркери рахують конволюцію паралельно (асинхронні виклики Pyro4) і повертають готові рядки.
4. Master склеює смуги по порядку і записує результат.

Межі зображення обробляються копіюванням крайнього пікселя (replicate). Результат **ідентичний** послідовному варіанту (перевірено з `scipy.ndimage.correlate`, різниця = 0).
Складність: O(W·H·k²·C) обчислень; на воркер — 1/N від цього. Комунікація: смуга + 2r рядків туди, смуга назад.

## Структура

```
solver.py                  # PARCS-розв'язувач (master: solve, worker: convolve_strip)
tools/make_input.py        # jpg/png -> input.txt (параметри + PPM P3)
tools/decode_output.py     # output.txt -> png + статистика часу
tools/run_benchmark.py     # автозапуск задач для N=1..4 через API PARCS -> results.csv
tools/plot_results.py      # results.csv -> графік
cloud/setup_gcp.sh         # створити master + 4 workers у GCP
cloud/startup.sh           # startup-скрипт VM: Python 2.7 + PARCS + запуск вузла
cloud/teardown_gcp.sh      # видалити все після здачі
cloud/requirements-py27.txt# перевірені версії бібліотек для Python 2.7
samples/test_image.png     # тестове зображення 1024x768
results_local/             # результати локального тесту
```

## Формат input.txt

```
filter=gauss size=7 sigma=2.0 workers=0 mode=par
P3
1024 768
255
r g b r g b ...
```
`workers=0` — усі увімкнені воркери, `workers=K` — лише перші K; `mode=seq` — послідовний варіант (рахує master).

## Швидкий старт у Google Cloud (Cloud Shell)

```bash
git clone https://github.com/<твій-логін>/parcs-image-filter && cd parcs-image-filter
gcloud projects create parcs-blur-andrushchenko      # або існуючий проєкт; прив'яжи billing у консолі
PROJECT_ID=parcs-blur-andrushchenko MY_IP=<твій IP з ifconfig.me> bash cloud/setup_gcp.sh
# почекати 3-5 хв, відкрити http://<MASTER_EXTERNAL_IP>:8080/workers  -> має бути 4 воркери

pip install --user pillow requests matplotlib
python3 tools/run_benchmark.py --master http://<MASTER_EXTERNAL_IP>:8080 --size 7 --sigma 2.0 --repeats 3
python3 tools/plot_results.py results/results.csv results/chart.png

bash cloud/teardown_gcp.sh                            # після здачі!
```

Ручний запуск через веб-інтерфейс: `Add Job` → solution = `solver.py`, input = файл з `tools/make_input.py`.

## Виправлення для застарілих версій

| Проблема | Як виправлено |
|---|---|
| `gcloud compute instances create-with-container` (з методички) не працює: Google вимкнув container startup agent з 31.07.2026 | VM на Debian 12 + `startup-script` (`cloud/startup.sh`), без контейнера |
| PARCS-Python написаний на Python 2.7 (`ConfigParser`, `Queue`, `Pyro4.async`), а в сучасних ОС Python 2 немає; базовий образ `debian:stretch` у Dockerfile застарів | Python 2.7 ставиться з conda-forge через `micromamba` |
| `ImportError: No module named cpuinfo` — `pip install py-cpuinfo` тягне 9.0.0, яка лише для Python 3 | `py-cpuinfo==4.0.0` |
| Без фіксації версій pip може підтягнути несумісні пакети | усі версії зафіксовані в `cloud/requirements-py27.txt` |
