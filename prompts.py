DEFAULT_PROMPT = """
Ini adalah nota pembelian, ambil data dan tampilkan hasilnya dalam bentuk JSON. Dalam gambar bisa berisi lebih dari satu nota, jadi pastikan untuk mengekstrak semua data yang ada. Jika dalam gambar tidak ada data, kembalikan array kosong.

Berikut kolom yang harus diisi
- tanggal dan waktu transaksi dalam format %d/%m/%Y %H:%M:%S (Jika tidak ada %d/%m/%Y, gunakan 01/01/1970. Jika tidak ada %H:%M:%S, gunakan 00:00:00) [nama key JSON: waktu]
- nama penjual (jika tidak ada, isi dg -) [nama key JSON: penjual]
- nama barang (jika tidak ada, isi dg -) [nama key JSON: barang]
- subtotal (pada gambar biasanya berada pada kolom paling kanan. merupakan hasil perkalian antara harga satuan barang x jumlah barang) [nama key JSON: subtotal]
- jumlah barang (jika tidak ada, isi dg 1. biasanya berada pada kolom paling kiri) [nama key JSON: jumlah]
- harga satuan barang (jika tidak ada, isi dg sub_total. jika tidak ditemukan, hitung berdasarkan kolom subtotal/jumlah) [nama key JSON: harga]
- service (jika tidak isi dg 0) [nama key JSON: service]
- pajak (jika tidak isi dg 0) [nama key JSON: pajak]
- pajak pertambahan nilai (PPN) (jika tidak isi dg 0) [nama key JSON: ppn]

PENTING:
1. Kembalikan respons HANYA dalam format JSON array tanpa penjelasan tambahan
2. JANGAN gunakan markdown code blocks (```) atau format lainnya
3. JANGAN tambahkan teks sebelum atau sesudah JSON
4. Format yang benar: [{"waktu": "...", "penjual": "...", ...}, {...}]
5. Jika hanya ada satu item, tetap kembalikan sebagai array dengan satu elemen
6. RESPON DENGAN CEPAT dan langsung ke JSON tanpa berpikir terlalu lama
7. Jangan tambahkan emoji atau karakter lain sebelum JSON
"""

TEXT_PROMPT = """
Ini adalah teks pesan yang berisi data pembelian/nota. Ambil data dan tampilkan hasilnya dalam bentuk JSON ARRAY.

PENTING: Pesan biasanya berisi BEBERAPA ITEM/BARANG yang berbeda. Setiap baris dengan tanda "-" atau bullet point adalah ITEM TERPISAH yang harus dijadikan OBJEK JSON TERPISAH dalam array.

Jika dalam teks tidak ada data pembelian, kembalikan array kosong.

Berikut kolom yang harus diisi untuk SETIAP ITEM:
- tanggal dan waktu transaksi dalam format %d/%m/%Y %H:%M:%S (Jika tidak ada tanggal, gunakan tanggal hari ini. Jika tidak ada waktu, gunakan 00:00:00) [nama key JSON: waktu]
- nama penjual (jika tidak ada, isi dg -) [nama key JSON: penjual]
- nama barang (jika tidak ada, isi dg -) [nama key JSON: barang]
- subtotal (total harga untuk setiap item. biasanya ada angka dengan 'k' untuk ribuan atau 'm' untuk jutaan) [nama key JSON: subtotal]
- jumlah barang (jika tidak ada, isi dg 1) [nama key JSON: jumlah]
- harga satuan barang (jika tidak ada, hitung berdasarkan subtotal/jumlah) [nama key JSON: harga]
- service (jika tidak ada, isi dg 0) [nama key JSON: service]
- pajak (jika tidak ada, isi dg 0) [nama key JSON: pajak]
- pajak pertambahan nilai (PPN) (jika tidak ada, isi dg 0) [nama key JSON: ppn]

CONTOH TEKS:
"selamat sore bapak/ibu mohon maaf untuk pengajuan tambhana buat fullback🙏 pak @Unknown number
- Pertamina dex HDD 75L(3drigen):1.125k
- Pertamina dex exsa 50L(2drigen):750k
- Pertamax 50L (2 drigen ):637k
- busi untuk alcon (2pcs):50k
total :Rp.2.562.000"

CONTOH OUTPUT YANG DIHARAPKAN:
[
  {
    "waktu": "19/12/2024 00:00:00",
    "penjual": "-",
    "barang": "Pertamina dex HDD 75L(3drigen)",
    "harga": 375000,
    "jumlah": 3,
    "service": 0,
    "pajak": 0,
    "ppn": 0,
    "subtotal": 1125000
  },
  {
    "waktu": "19/12/2024 00:00:00",
    "penjual": "-",
    "barang": "Pertamina dex exsa 50L(2drigen)",
    "harga": 375000,
    "jumlah": 2,
    "service": 0,
    "pajak": 0,
    "ppn": 0,
    "subtotal": 750000
  },
  {
    "waktu": "19/12/2024 00:00:00",
    "penjual": "-",
    "barang": "Pertamax 50L (2 drigen )",
    "harga": 318500,
    "jumlah": 2,
    "service": 0,
    "pajak": 0,
    "ppn": 0,
    "subtotal": 637000
  },
  {
    "waktu": "19/12/2024 00:00:00",
    "penjual": "-",
    "barang": "busi untuk alcon (2pcs)",
    "harga": 25000,
    "jumlah": 2,
    "service": 0,
    "pajak": 0,
    "ppn": 0,
    "subtotal": 50000
  }
]

PENTING:
1. EKSTRAK SEMUA ITEM yang ada dalam pesan! Jika ada 4 item, harus ada 4 objek dalam array
2. Setiap baris dengan tanda "-" atau item terpisah = objek JSON terpisah
3. Kembalikan respons HANYA dalam format JSON array tanpa penjelasan tambahan
4. JANGAN gunakan markdown code blocks (```) atau format lainnya
5. JANGAN tambahkan teks sebelum atau sesudah JSON
6. Format yang benar: [{"waktu": "...", "penjual": "...", ...}, {...}, {...}, {...}]
7. Jika hanya ada satu item, tetap kembalikan sebagai array dengan satu elemen
8. Angka dengan 'k' berarti ribu (contoh: 1.125k = 1125000)
9. Angka dengan 'm' berarti juta (contoh: 2.5m = 2500000)
10. RESPON DENGAN CEPAT dan langsung ke JSON tanpa berpikir terlalu lama
11. Jangan tambahkan emoji atau karakter lain sebelum JSON
12. Abaikan baris "total" - jangan jadikan item terpisah
"""