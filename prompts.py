DEFAULT_PROMPT = """
Ini adalah nota pembelian, ambil data dan tampilkan hasilnya dalam bentuk JSON.

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
"""