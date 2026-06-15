Pilih satu gambar terbaik untuk featured image WordPress dari daftar kandidat yang diberikan.

Prioritas:
- paling relevan dengan isi post
- subjek utama terlihat jelas
- subjek utama tidak harus satu orang, malah lebih baik kalau banyak orang
- foto yang menunjukkan ekspresi bahagia atau senang lebih diutamakan
- komposisi cocok sebagai gambar sampul artikel
- hindari gambar blur, terlalu gelap, terlalu ramai, duplikat, atau terlalu banyak teks jika ada pilihan yang lebih baik
- gunakan URL publik dan filename yang diberikan untuk menilai kandidat

Kembalikan JSON saja dengan format berikut:

{
  "selected_image": "image-x.jpg",
  "selected_url": "https://example.com/uploads/image-x.jpg",
  "reason": "alasan singkat"
}

Aturan output:
- `selected_image` wajib diisi
- `selected_url` wajib diisi
- `selected_image` dan `selected_url` harus menunjuk ke kandidat yang sama
