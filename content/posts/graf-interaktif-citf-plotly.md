---
title: "Animasi interaktif berdasarkan data CITF menggunakan Plotly"
date: 2021-08-25T04:59:55+08:00
---

Saya gemar melayari subreddit r/dataisbeautiful dan melihat graf hasil buatan pengguna Reddit lain di sana. Salah satu jenis graf yang saya paling minat adalah apabila graf itu seolah-olah animasi, berubah selaras mengikut jangka masa waktu yang semakin bertambah. Kita boleh melihat perkembangan sesuatu data itu dari mula hingga ke akhir. 

Contoh post terbaru di subreddit itu yang mempunyai graf sebegini adalah seperti graf di bawah yang memaparkan Kadar vaksinasi sebahagian daripada negara-negara di seluruh dunia (*sayang Malaysia tidak dimasukkan sekali di sini*):

{{< rawhtml >}}
<iframe id="reddit-embed" src="https://www.redditmedia.com/r/dataisbeautiful/comments/p7l5rm/oc_the_race_to_vaccinate/?ref_source=embed&amp;ref=share&amp;embed=true" sandbox="allow-scripts allow-same-origin allow-popups" style="border: none;" height="620" width="640" scrolling="no"></iframe>
{{< /rawhtml >}}

Sebelum ini saya menganggap animasi sebegini rumit untuk dilakukan tetapi apabila pihak CITF telah melancarkan [public repo](https://twitter.com/Khairykj/status/1410164953965752331?s=20) di Github bagi data vaksinasi Malaysia, saya memutuskan untuk cuba menghasilkan semula gaya visualisasi ini menggunakan data tersebut.

Seterusnya saya akan menerangkan langkah-langkah yang diperlukan untuk menghasilkan visualisasi seperti yang di bawah. Sebagai rujukan, code penuh yang saya gunakan di sini boleh didapati di [sini](https://github.com/pokgak/citf-graphs/blob/main/main.py).

{{< rawhtml >}}
<iframe id="pokgak-citf" src="https://pokgak.github.io/citf-graphs/" style="border: none;" height="400" width="640" scrolling="no"></iframe>
{{< /rawhtml >}}

## Pembersihan Data

Dalam projek yang melibatkan data sebegini, data boleh datang dari pelbagai sumber dan bentuk. Oleh itu, langkah pertama selalunya adalah pembersihan data. Tujuan langkah ini adalah supaya pada akhirnya kita mempunyai data dalam format yang sesuai dan boleh terus digunakan untuk langkah seterusnya tanpa perlu pemprosesan ekstra apa-apa pun.

Saya bernasib baik kali ini kerana sumber data yang dibekalkan oleh pihak CITF Malaysia sudah pun berada dalam format CSV yang senang untuk dibaca menggunakan `pandas`, sebuah library untuk memanipulasi data menggunakan Python. Pihak CITF tidak menawarkan public REST API yang boleh digunakan untuk mengambil (fetch) data tersebut maka saya terpaksa mengambil data menerusi Github. Proses ini kurang sesuai jika anda mahu menapis dahulu data yang diambil tapi untuk kegunaan saya ini, kaedah ini adalah mencukupi.

```python
STATE_DATA_URL = "https://raw.githubusercontent.com/CITF-Malaysia/citf-public/main/vaccination/vax_state.csv"

df = pd.read_csv(StringIO(requests.get(data_url).text))
```

Function `read_csv` akan mengambil output data yang diambil dari Github dan menukarkannya ke format DataFrame yang digunakan oleh library pandas. Format DataFrame adalah 2D seakan-akan Excel. Ia mempunyai rows dan columns yang mempunyai data dan menawarkan fungsi-fungsi untuk memanipulasi data tersebut (gabung, pisah, transpose, etc) dengan mudah. Berikut adalah code yang saya gunakan untuk menyiapkan data raw tadi untuk visualisasi:

```python
df.set_index(["date", "state"])
  .loc[:, ["cumul_partial", "cumul_full", "cumul"]]
  .rename(columns={"cumul_partial": "partially_vaxed", "cumul_full": "fully_vaxed"})
  .sort_values(by="cumul", ascending=False)
  .sort_index(level="date", sort_remaining=False)
  .reset_index()
```

Secara ringkasnya, 

1. `set_index`: saya menetapkan column "date" dan "state" index DataFrame tersebut yang akan saya gunakan nanti untuk mengasingkan data vaksinasi mengikut tarikh dan negeri 
2. `loc`: pilih hanya column yang saya mahu 
3. `rename`: memberikan nama baharu kepada column-column tersebut supaya lebih mudah difahami 
4. `sort_values`: susun semua data vaksinasi mengikut jumlah kumulatif ("cumul")
5. `sort_index`: susun semua data vaksinasi mengikut tarikh
6. `reset_index`: menjadikan column index dari langkah 1 sebelum ini balik seperti column biasa yang boleh digunakan secara normal

Untuk mengetahui lebih lanjut fungsi functions yang saya pakai di sini, bolehlah rujuk kepada [pandas API Reference](https://pandas.pydata.org/pandas-docs/stable/reference/index.html).

## Visualisasi Data menggunakan Plotly

[Plotly](https://plotly.com/graphing-libraries/) adalah sebuah library yang menawarkan fungsi-fungsi untuk mempermudah pengguna untuk menghasilkan visualisasi interaktif. Ia ditawarkan dalam bahasa Python, R, ataupun JavaScript. Saya berpeluang untuk menggunakan Plotly dalam Python untuk menghasilkan visualisasi untuk thesis bachelor saya dan berdasarkan pengalaman saya, sangat mudah untuk bereksperimen dan menghasilkan graf visualisasi menarik menggunakan library ini.

Ciri Plotly yang sangat bagus adalah [Plotly Express](https://plotly.com/python/plotly-express/). Untuk kebanyakan fungsi visualisasi, Plotly Express sudah cukup pandai menakrif data yang diberikan dan kemudian menghasilkan visualisasi seperti yang dikehendaki. Berikut adalah code yang saya gunakan untuk menghasilkan animasi graf yang saya paparkan di permulaan blog post ini:

```python
fig = px.bar(
        state_data,
        x="state",
        y=["partially_vaxed", "fully_vaxed"],
        animation_frame="date",
        animation_group="state",
        labels={"value": "Total vaccinated", "state": "", "variable": "Dose Type"},
        title="Vaccination Count in Malaysia by State",
    )
```

Jika anda perasan, saya hanyalah menggunakan **satu** function sahaja daripada Plotly Express iaitu `bar`. Function ini digunakan untuk menghasilkan visualisasi graf bar. Sebagai parameter, saya berikan data vaksinasi yang telah dibersihkan dan ditukarkan ke format DataFrame. Menerusi parameter `x` dan `y`, saya menetapkan data daripada column manakah dalam DataFrame tersebut yang akan digunakan sebagai paksi X dan paksi Y dalam graf.

Seterusnya, untuk menghasilkan animasi bergerak, saya menggunakan parameter `animation_frame` dan ditetapkan column "date" sebagai nilainya (value). Dengan parameter ini, Plotly akan menghasilkan satu graf untuk setiap nilai dalam column tersebut. Jadi bila saya menggunakan column "date", Plotly akan menghasilkan satu graf untuk setiap tarikh dalam data vaksinasi. Untuk menghasilkan animasi, graf-graf ini akan disusun mengikut tarikh dan dipaparkan seolah-olah slideshow. Hasil akhirnya kita akan dapat perkembangan kadar vaksinasi selaras dengan masa.

Parameter `animation_frame` cukup untuk menghasilkan animasi perkembangan kadar vaksinasi tersebut tetapi animasinya kelihation tidak begitu lancar dan seperti terpotong-potong. Oleh itu, saya juga menggunakan parameter `animation_group`. Dengan parameter ini, Plotly akan mencuba untuk melancarkan transisi antara dua graf yang dihasilkan berdasakan nilai column dalam `animation_frame` tadi.
Dalam visualisasi graf bar, Plotly akan menunjukkan pertukaran posisi bar tersebut apabila ia berubah kedudukan. Dengan ini animasi kita tadi telah pun menjadi lebih lancar.

Akhir sekali, parameter `labels` dan `title` digunakan untuk menetapkan label yang lebih mesra pembaca untuk legend, paksi, serta tajuk graf.

# Konklusi

Saya amat berpuas hati dengan animasi graf ini kerana saya telah belajar cara untuk menghasilkan jenis bentuk graf yang telah saya minati buat sekian lama. Namun begitu, walaupun graf ini kelihatan lebih cantik berbanding graf lain dengan animasi bergerak, saya akui apa yang telah saya hasilkan ini lebih kepada latihan menggunakan library Plotly itu sendiri. Masih banyak aspek yang boleh diperbaiki untuk menyampaikan maklumat menggunakan graf secara tepat dan efektif. 

Untuk mengakses segala code yang telah saya tunjukkan di sini, boleh akses repository [pokgak/citf-graphs](https://github.com/pokgak/citf-graphs) di Github. Saya juga telah menetapkan jadual berkala supaya graf visualisasi tersebut dikemas kini setiap hari menggunakan Github Actions. Blog post cara saya bagaimana saya buat akan datang.


