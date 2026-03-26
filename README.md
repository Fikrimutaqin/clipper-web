# Clipper Web (SaaS)

Aplikasi web cerdas untuk menemukan video YouTube (khususnya Podcast/Trending), mengunduhnya, mencari momen terbaik secara otomatis (menggunakan AI), memotong video, dan mengunggahnya kembali ke YouTube Anda (baik sebagai video reguler maupun YouTube Shorts).

## Fitur Utama

- **OAuth2 Google/YouTube Login:** Autentikasi aman untuk mengelola *channel* YouTube Anda.
- **YouTube Discovery & Search:** Secara otomatis menampilkan daftar video Podcast populer di Indonesia, beserta fitur pencarian langsung dari API YouTube.
- **Video Downloader:** Mengunduh video utuh dari YouTube langsung ke dalam server.
- **AI Highlight Suggestion:** Menganalisis *peak* audio pada video untuk merekomendasikan *timestamp* (start/end) terbaik yang bisa dipotong.
- **Video Clipper (PyAV):** Memotong video secara akurat tanpa *re-encode* eksternal. Mendukung konversi video Landscape (16:9) menjadi format Vertikal (9:16) secara proporsional (tanpa distorsi) untuk keperluan YouTube Shorts.
- **Auto Upload:** Mengunggah hasil *clipping* kembali ke *channel* YouTube Anda secara otomatis.

## Prasyarat

Pastikan Anda telah menginstal:
- **Python 3.10+ (Recommended: 3.12+)**

Catatan penting untuk macOS: hindari *system Python* (contoh 3.9.6) karena sering memakai LibreSSL dan memunculkan warning/masalah kompatibilitas pada beberapa dependency (mis. `urllib3`).

## Instalasi

1. **Clone repositori ini atau masuk ke direktori proyek:**
   ```bash
   cd clipper-web
   ```

2. **Buat virtualenv (disarankan):**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   ```

3. **Instal dependensi Python:**
   ```bash
   pip install -r requirements.txt
   ```
   *Library utama yang digunakan: `fastapi`, `uvicorn`, `av` (PyAV), `yt-dlp`, `google-api-python-client`.*

4. **Konfigurasi Google OAuth2:**
   Anda perlu membuat kredensial OAuth2 di [Google Cloud Console](https://console.cloud.google.com/):
   - Buat *Project* baru.
   - Aktifkan **YouTube Data API v3**.
   - Masuk ke menu *Credentials* -> *Create Credentials* -> *OAuth client ID*.
   - Tambahkan URI *Redirect* menjadi: `http://localhost:8000/auth/google/callback`
   - Salin *Client ID* dan *Client Secret*.
   - Set variabel environment (di terminal atau file `.env` jika Anda menggunakan *dotenv*):
     ```bash
     export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
     export GOOGLE_CLIENT_SECRET="your-client-secret"
     ```

## Menjalankan Server

Jalankan aplikasi menggunakan Uvicorn:

```bash
python3 -m uvicorn main:app --reload --port 8000
```

Buka browser Anda dan kunjungi: **http://127.0.0.1:8000**

## Troubleshooting (macOS)

Jika Anda melihat warning seperti:
- `NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+ ... LibreSSL ...`
- `FutureWarning: non-supported Python version (3.9.6) ...`

Solusi yang disarankan:
- Pakai Python 3.10+ dan jalankan aplikasi di dalam virtualenv (`.venv`) seperti langkah instalasi di atas.
- Pastikan menjalankan server dengan interpreter dari `.venv` (cek `which python` setelah `source .venv/bin/activate`).

## Cara Penggunaan

1. Klik **"Lanjut dengan YouTube"** di halaman awal dan selesaikan proses login.
2. Di tab **Discovery Video**, pilih salah satu video Podcast atau cari video yang Anda inginkan.
3. Klik **Gunakan Video Ini** untuk mengunduhnya ke server lokal.
4. Setelah unduhan selesai, Anda akan dialihkan ke tab **Clipper Tool**.
5. Pilih **Format Video** (Reguler atau YouTube Shorts).
6. (Opsional) Klik **AI Rekomendasikan Waktu** untuk mendapatkan saran pemotongan video otomatis.
7. Tentukan *start* dan *end* detik, isi judul, lalu klik **Mulai Buat Clip**.
8. Cek *progress* di tab **Status & Jobs**. Jika Anda mencentang opsi "Upload ke YouTube", video otomatis akan diunggah ke channel Anda.

## Struktur Folder Penyimpanan

Saat aplikasi berjalan, folder `storage` akan dibuat secara otomatis dengan struktur berikut:
- `storage/uploads/`: Menyimpan file video yang di-upload manual.
- `storage/downloads/`: Menyimpan video mentah yang diunduh dari YouTube (`yt-dlp`).
- `storage/clips/`: Menyimpan video hasil potongan (siap tonton/upload).
- `storage/app.db`: Database SQLite lokal untuk mencatat sesi, user, dan job status.

## Catatan Tentang YouTube Shorts
Untuk memastikan video Anda dikenali sebagai **Shorts** oleh algoritma YouTube:
- Pilih mode **YouTube Shorts (Vertikal 9:16)** saat melakukan pemotongan.
- Pastikan durasi akhir (selisih *start* dan *end*) **kurang dari 60 detik**.

---
*Dikembangkan dengan FastAPI & PyAV.*
