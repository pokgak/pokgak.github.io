---
title: "Pengenalan Github Actions"
date: 2021-08-24T04:49:42+08:00
---

Github Actions (GA) adalah servis automation yang ditawarkan oleh Github untuk semua penggunanya. Jika anda mempunyai repository public di Github, anda boleh mula menggunakan Github Actions pada saat ini tanpa perlu membayar apa-apa pun!


## Bagaimana untuk mula dengan Github Actions?

Untuk mula menggunakan Github Actions, anda boleh pergi ke mana-mana repository public yang anda miliki dan seterusnya pergi ke tab Actions.

![](images/actions-tab.png)

Jika anda belum pernah setup mana-mana workflow di repository tersebut, anda akan melihat pilihan templates siap yang boleh digunakan untuk pelbagai jenis projek. Sebagai pemula, saya cadangkan anda mula dengan template barebones yang ditawarkan.

![](images/actions-get-started.png)

Anda boleh menggunakan editor local di komputer sendiri tapi Github juga ada menawarkan editor online di mana fail workflow anda akan diperiksa formatnya secara langsung sambil anda menaip. Github akan highlight jika fail workflow anda mempunyai kesalahan yang membuatkan workflow anda akan gagal. Selain itu juga, di tepi editor online itu ada dipaparkan documentation ringkas mengenai syntax fail workflow jadi anda tidak perlu lagi tukar-tukar tab untuk semasa menulis fail workflow anda.

![Github Actions online Editor](images/actions-editor.png)

## Anatomi fail workflow Github Actions

Saya telah beberapa kali menyebut "fail workflow" dalam perenggan sebelum ini tapi belum pernah menerangkan apakah fail workflow itu. Github Actions menggunakan fail workflow untuk menetapkan bagaimana untuk melakukan automasi. Fail ini ditulis dalam format YAML. Satu ciri-ciri penting yang saya mahu highlight di sini adalah format YAML adalah whitespace-sensitive, bermakna anda perlu pastikan indentation fail workflow anda menggunakan 4 spaces.

Sebelum bermula, ini adalah isi akhir fail workflow contoh kita:

```yaml
jobs:
  job-pertama:
    runs-on: ubuntu-latest
      steps:
        - run: echo Hello, world!

        - name: Selamat tinggal dunia
          run: echo Bye, world!

        - uses: actions/checkout@v2
```

Ikuti penjelasan saya di bawah untuk memahami apakah yang akan dilakukan apabila workflow ini dijalankan.

## Keyword dalam fail workflow Github Actions

Dalam fail workflow anda ada dua top-level keyword yang wajib: `on` dan `jobs`.

### Keyword `on`

Satu ciri-ciri penting Github Actions adalah, workflow anda perlu dimulakan melalui "triggers". Hampir semua aktiviti yang anda boleh lakukan secara manual di Github boleh dijadikan trigger untuk workflow anda. Sebagai contoh, anda boleh menetapkan workflow untuk dijalankan apabila seseorang telah push codenya ke repo, atau apabila pull request baru dibuka. Ini cara bagaimana anda melakukan kedua-dua contoh tersebut:

```yaml
on:
  push:
  pull_request:
```

Keyword `on` digunakan untuk menanda bahawa semua keyword dibawahnya adalah event-event dimana fail workflow anda patut dijalankan. `push` bermakna apabila seseorang telah push codenya ke repo anda, maka Github Actions akan menjalankan fail workflow tersebut. `pull_request` pula bermakna jika seseorang telah membuka pull request (PR) baru di repository anda, maka fail workflow tersebut akan dijalankan.

Kedua-dua keyword `push` dan `pull_request` ini juga boleh menerima sub-keyword lain untuk tujuan menapis dengan lebih spesifik bila workflow itu patut dijalankan. Antara sub-keyword yang boleh digunakan adalah `branches` untuk menapis hanya push atau pull request kepada branch yang dinyatakan sahaja. Anda juga boleh menapis mengikut lokasi fail code anda di dalam repo menggunakan sub-keyword `paths`.

Terdapat banyak lagi keyword yang anda boleh gunakan untuk trigger workflow anda, jika berminat boleh pergi ke page [ini](https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions#on) dan [ini](https://docs.github.com/en/actions/reference/events-that-trigger-workflows#webhook-events) untuk membaca lebih lanjut.

### Keyword `jobs`

Okay, kita telah tetapkan **bila** workflow ini patut dijalankan menggunakan keyword `on`. Seterusnya kita akan menetapkan **apa** yang workflow ini patut buat menggunakan keyword [`jobs`](https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions#jobs). Sesebuah workflow mestilah mempunyai paling kurang satu job. Untuk mencipta job baru, anda boleh menggunakan apa-apa perkataan sebagai `id` cuma perlu dipastikan tiada space. Contohnya seperti berikut:

```yaml
jobs:
  job-pertama:
    runs-on: ubuntu-latest
```

Di sini, `job-pertama` adalah `id` untuk job kita. Seterusnya, setiap job perlulah menetapkan di bawah environment manakah job ini akan dijalankan. Github Actions menawarkan platform Windows, Linux, dan macOS yang anda boleh gunakan secara percuma. Senarai penuh versi yang disokong boleh dibaca di [halaman](https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions#jobsjob_idruns-on) ini. Di sini saya menggunakan `ubuntu-latest` yang bermakna, job ini akan dijalankan di platform Ubuntu yang terbaru (pada masa tulisan ini adalah Ubuntu 20.04.

Setelah menetapkan platform, tiba masa untuk kita senaraikan apakah yang patut workflow kita ini buat. Untuk itu kita perlukan keyword `steps`. Seperti keyword `jobs`, keyword `steps` mengandungi sub-keywords yang, satu untuk setiap apa yang kita mahu jalankan.

Setiap satu step akan dimulakan dengan simbol `-`. Dalam syntax YAML, ini menandakan bahawa semua keyword di bawah satu `-` adalah satu bahagian. Keyword `run` digunakan untuk menjalankan command seolah-olah anda berada di terminal platform yang telah dipilih menggunakan keyword `runs-on` sebelum ini.

```yaml
jobs:
  job-pertama:
    runs-on: ubuntu-latest
      steps:
        - run: echo Hello, world!

        - name: Selamat tinggal dunia
          run: echo Bye, world!
```

Dalam contoh di atas, saya telah menetapkan step itu untuk run command `echo`. Command ini akan print perkataan selepas itu ke terminal anda, dalam kes ini anda akan melihat "Hello, world" di log result workflow anda nanti. Dalam contoh di atas juga, saya telah menetapkan workflow ini untuk run command echo tapi kali ini dengan perkataan lain pula. Selain daripada keyword `run`, setiap step juga boleh ditetapkan dengan keyword-keyword lain seperti `name`, `id` dan pelbagai lagi. Senarai penuh boleh anda lihat di [halaman](https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions#jobsjob_idsteps) ini. Fungsi simbol `-` di sini adalah untuk membantu mengumpul semua keyword yang berkaitan dengan step itu. Setiap simbol `-` bermakna satu step dalam job itu.

### Keyword `uses`

Kita telah melihat bagaimana cara untuk menjalankan sebarang command melalui keyword `run`. Untuk sesetengah perkara, sekadar bergantung kepada command mungkin akan membataskan apa yang anda boleh lakukan. Oleh itu, Github Actions juga mempunyai fungsi untuk memanggil code luar dari fail workflow anda. Code ini boleh berasal dari repo yang sama ataupun daripada repo developer lain di Github.

Actions ini boleh ditulis dengan pelbagai cara sama ada menggunakan Javascript atau melalui Docker. Github juga menyediakan [marketplace](https://github.com/marketplace?type=actions) untuk anda mencari actions yang sesuai untuk digunakan dalam fail workflow anda. Github sendiri mempunyai beberapa Actions yang essential seperti [checkout](https://github.com/marketplace/actions/checkout) untuk checkout git repo anda sewaktu workflow dijalankan dan juga [setup-node](https://github.com/actions/setup-node) untuk setup environment node/javascript anda.

Untuk menggunakan Actions, ada perlu menggunakan keyword `uses` diikuti dengan nama Actions yang ingin digunakan. Kebanyakan Actions juga mempunya keyword tersendiri yang digunakan untuk memperincikan bagaimana Actions tersebut dijalankan.

```yaml
jobs:
  job-pertama:
    runs-on: ubuntu-latest
      steps:
        - run: echo Hello, world!

        - name: Selamat tinggal dunia
          run: echo Bye, world!

        - uses: actions/checkout@v2
```

Dalam contoh di atas, saya menggunakan Actions dari Github `actions/checkout` untuk melakukan git checkout repo saya ke sewaktu workflow dijalankan. `@v2` di bahagian belakang itu menandakan versi Action tersebut yang ingin saya gunakan. Versi yang ditawarkan oleh Action tersebut boleh disemak di page Releases Action tersebut.

## Konklusi

Saya pernah menggunakan Jenkins dan Bitbucket Pipeline dan berdasarkan pengalaman saya Github Actions adalah jauh lebih baik dari kedua-dua produk CI/CD tersebut. Dokumentasi Github Actions yang ditawarkan Github adalah sangat lengkap. Saya paling banyak merujuk halaman [Workflow Syntax](https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions) semasa mula belajar menggunakan Github Actions. Selain itu, halaman-halaman lain dalam [Reference](https://docs.github.com/en/actions/reference) ini juga sangat membantu anda ingin mula melakukan perkara yang lebih advance dengan Github Actions.

Antara contoh automation yang pernah saya lakukan menggunakan Github Actions adalah, menjalankan unit test untuk setiap commit push, memeriksa dan baiki tajuk pull request secara automatik jika tidak memenuhi kriteria anda. Saya juga pernah menggunakan Github Actions workflow untuk melakukan DB dump daripada server dan terus upload ke S3. Pada pandangan saya, Github Actions sangat menarik dan macam-macam yang anda boleh lakukan dengannya.

