---
title: "Auto-update Graf Covid-19 menggunakan Github Actions"
date: 2021-09-02T09:56:10+08:00
tags: [Github Actions, CI/CD]
---

Dalam blog post saya sebelum ini saya dah menerangkan bagaimana saya membuat graf animasi [perkembangan status pemberian imunisasi][1] negeri-negeri di Malaysia. Seterusnya saya juga ada berkongsi [asas-asas untuk menggunakan Github Actions][2]. Dalam blog post ini saya ingin menerangkan pula bagaimana saya menggunakan Github Actions untuk mengemaskini graf tersebut dengan data terbaru yang dikeluarkan oleh pihak CITF Malaysia secara automatik setiap hari.

## Konfigurasi penuh

Sebelum saya mula penerangan, inilah hasil fail workflow Github Actions yang saya gunakan:


```yaml
name: Update Graphs

on:
  push:
    branches: [main]
  workflow_dispatch:
  schedule:
    - cron: "0 0 * * *" # Run workflow everyday at 12 AM 
jobs:
  vax-count-by-state:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-python@v2
        with:
          python-version: "3.8"

      - name: Cache pip
        uses: actions/cache@v2
        with:
          # This path is specific to Ubuntu
          path: ~/.cache/pip
          # Look to see if there is a cache hit for the corresponding requirements file
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-
            ${{ runner.os }}-

      - name: Install dependencies
        run: pip3 install -r requirements.txt

      - name: Fetch latest data & generate new graph
        run: python3 main.py
        
      - id: get-date
        run: echo "::set-output name=value::$(date --iso-8601)"

      - uses: stefanzweifel/git-auto-commit-action@v4
        with:
          commit_message: "bot: update graph for ${{ steps.get-date.outputs.value }}"
```

## Bahagian-bahagian

Saya akan memecahkan penerangan saya kepada beberapa bahagian iaitu:

1. Jadual auto-update
2. Melakukan kemaskini graf
3. Commit & Push kemaskini ke repository

### Bahagian 1: Jadual Auto-update

Di bahagian ini saya akan menunjukkan cara bagaimana saya menetapkan Github Actions untuk melakukan kemaskini setiap hari secara automatik.

Dalam penerangan saya berkenaan [asas-asas Github Actions][2], saya ada menyebut yang sesebuah workflow itu boleh dicetuskan oleh pelbagai event daripada Github. Antara event yang disokong adalah menjalankan workflow tersebut berdasarkan jadual yang ditetapkan. Untuk ini kita memerlukan keyword `schedule` di bawah keyword utama `on` seperti contoh di bawah:

```yaml
on:
  schedule:
    - cron: "0 0 * * *" # Run workflow everyday at 12 AM
```

Keyword `schedule` ini menerima jadual dalam format syntax `cron`. Jika anda tahu selok-belok sesebuah sistem UNIX atau Linux anda mungkin tahu mengenai `cron`. Untuk yang belum tahu apa syntax `cron` itu, ia mempunyai 5 bahagian yang dipisahkan dengan paling kurang satu karakter `whitespace` seperti `space` atau `tab`. Bermula dari kiri, bahagian-bahagian tersebut melambangkan nilai berikut, nilai yang boleh diterima saya letakkan dalam kotak disebelah:

- minit [0 hingga 59]
- jam [0 hingga 23]
- hari dalam bulan [1 hingga 31]
- bulan dalam tahun [1 hingga 12]
- hari dalam minggu  [0 hingga 6], bermula dengan 0=Ahad, 1=Isnin, dan seterusnya hingga 6=Sabtu

Nilai khas `*` boleh digunakan yang membawa maksud *untuk setiap nilai dalam bahagian tersebut*. Dalam fail workflow saya jadual cron yang digunakan adalah "0 0 \* \* \*" yang bermakna, "*Jalankan fail workflow ini pada jam 0:00 (tengah malam) setiap hari dalam bulan, untuk setiap tahun, tidak mengira hari apa pun*". Kadangkala syntax cron ini boleh mengelirukan. Jadi saya mencadangkan laman [crontab.guru](https://crontab.guru/) untuk memeriksa dan bereksperimen dengan syntax cron ini.

### Bahagian 2: Melakukan kemaskini graf

Di blog post sebelum ini saya telah menerangkan code yang saya gunakan untuk menjana graf animasi baru jadi kita akan menggunakan skrip yang sama untuk melakukannya di sini. Walaupun begitu, sebelum menjalankan skrip Python untuk menjana graf berdasarkan informasi baru, kita perlu menyediakan semua perisian yang diperlukan oleh skrip tersebut di Github Actions Runner.

Untuk itu saya menggunakan [actions/setup-python] untuk menyediakan Python di runner tersebut dan seterusnya menginstall dependency lain. Hanya step terakhir dalam job tersebut adalah bahagian dimana saya betul-betul menjalan kerja tersebut.  Berikut adalah code tersebut.

```yaml
- uses: actions/checkout@v2
  with:
    token: ${{ secrets.GITHUB_TOKEN }}

- uses: actions/setup-python@v2
  with:
    python-version: "3.8"

- name: Cache pip
  uses: actions/cache@v2
  with:
    # This path is specific to Ubuntu
    path: ~/.cache/pip
    # Look to see if there is a cache hit for the corresponding requirements file
    key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
    restore-keys: |
      ${{ runner.os }}-pip-
      ${{ runner.os }}-            

- name: Install dependencies
  run: pip3 install -r requirements.txt

- name: Fetch latest data & generate new graph
  run: python3 main.py
```

### Bahagian 3: Commit dan Push kemaskini ke repository

Setelah mencipta graf baru dari data terkini daripada repo CITF-public, graf baru kita sudah pun ready tapi belum lagi dipaparkan di website https://pokgak.github.io/citf-graphs kerana ia masih belum dicommit lagi ke repository.

Biasanya saya akan melakukan commit secara manual dan push ke Github tapi oleh kerana kita melakukan semua proses diatas secara automatik daripada Github Actions, kita tidak boleh lagi buat begitu. Oleh itu, saya menggunakan Actions [stefanzweifel/git-auto-commit-action](https://github.com/stefanzweifel/git-auto-commit-action) untuk melakukan commit secara automatik. Berikut adalah segmen fail workflow saya yang menunjukkan penggunaan Actions ini:

```yaml
- uses: stefanzweifel/git-auto-commit-action@v4
  with:
    commit_message: "bot: update graph for ${{ steps.get-date.outputs.value }}"
```

Seperti yang anda boleh lihat, mudah sahaja cara penggunaan actions ini. Kita hanya perlu menggunakan keyword `uses` untuk menanda bahawa kita ingin menggunakan Actions luar dalam fail workflow ini, diikuti dengan nama Actions tersebut. Senarai semua actions yang ada boleh dilihat di [Github Actions Marketplace](https://github.com/marketplace?type=actions). Tambahan pula, anda juga boleh [menulis Actions anda sendiri](https://docs.github.com/en/actions/creating-actions)!.


## Konklusi 

Sejak adanya workflow ini, saya tidak perlu lagi memastikan graf yang saya hasilkan di [pokgak/citf-graphs](https://github.com/pokgak/citf-graphs) sentiasa dikemaskini dengan maklumat terbaru secara manual, semuanya dilakukan secara automatik. Sejak itu juga, Github menunjukkan aktiviti saya aktif setiap hari, walaupun pada hakikatnya itu semua adalah bot sahaja :p

![Cuba teka bila saya mula pakai workflow ni?](images/github-activity.png)


[1]: https://pokgak.xyz/articles/graf-interaktif-citf-plotly/
[2]: https://pokgak.xyz/articles/pengenalan-github-actions/
