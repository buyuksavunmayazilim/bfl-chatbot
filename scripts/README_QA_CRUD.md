# QA Embeddings CRUD Kullanımı

Bu doküman, `qa_embeddings` tablosundaki soru-cevap kayıtlarını Docker içindeki `api` servisi üzerinden yönetmek için kullanılan `scripts/qa_crud.py` aracını açıklar.

Araç aşağıdaki işlemleri destekler:

- Yeni soru-cevap kaydı ekleme
- Kayıtları listeleme ve filtreleme
- ID ile tek kayıt görüntüleme
- Soru, cevap, intent ve `is_augmented` alanlarını güncelleme
- Kayıt silme
- `BAAI/bge-m3` ile semantik benzerlik araması
- Mevcut kayıtların embeddinglerini yeniden üretme

## 1. Kullanılan model ve tablo yapısı

Embedding modeli:

```text
BAAI/bge-m3
```

Bu model 1024 boyutlu embedding üretir. Bu nedenle tablo kolonunun aşağıdaki tipte olması gerekir:

```sql
embedding vector(1024)
```

Beklenen tablo yapısı:

```sql
CREATE TABLE qa_embeddings (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    intent_category VARCHAR(64) NOT NULL,
    is_augmented BOOLEAN NOT NULL DEFAULT FALSE,
    embedding vector(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

> `BAAI/bge-m3` kullanılırken `vector(384)` kolonuna veri yazılamaz.

## 2. Dosya konumları

Önerilen proje yapısı:

```text
project-root/
├── alembic/
│   └── versions/
│       └── xxxx
├── app/
├── scripts/
│   └── qa_crud.py
├── Dockerfile
├── docker-compose.yml
├── .env
└── README_QA_CRUD.md
```

`qa_crud.py` dosyası container içerisinde şu konumda bulunmalıdır:

```text
/app/scripts/qa_crud.py
```

Dockerfile içinde proje dosyalarının image'a kopyalandığından emin olun:

```dockerfile
WORKDIR /app
COPY . /app
```

Compose dosyasında `.:/app` bind mount'u prod ortamında kapalı olduğu için yeni script veya migration eklendikten sonra API image'ı yeniden oluşturulmalıdır.

```bash
docker compose build api
docker compose up -d api
```

Alternatif olarak:

```bash
docker compose up -d --build api
```

## 3. Docker içindeki veritabanı bağlantısı

API container'ı PostgreSQL'e host makinenin yayınlanan `5438` portundan değil, Docker servis adı üzerinden bağlanmalıdır.

API container'ı için doğru değerler:

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=veritabani_adi
POSTGRES_USER=kullanici
POSTGRES_PASSWORD=sifre
```

Host bilgisayardan PostgreSQL'e bağlanırken ise port `5438` kullanılır:

```text
localhost:5438
```

Özet:

| Bağlantı yapan yer | Host | Port |
|---|---|---:|
| `api` container'ı | `postgres` | `5432` |
| Host bilgisayar / pgAdmin dış bağlantı | `localhost` | `5438` |

## 4. Gerekli Python paketleri

API image'ında aşağıdaki paketler bulunmalıdır:

```text
sentence-transformers
psycopg2-binary
pgvector
```

`requirements.txt` örneği:

```text
sentence-transformers
psycopg2-binary
pgvector
```

Paketler eklendikten sonra image yeniden build edilmelidir:

```bash
docker compose up -d --build api
```

## 5. Migration işlemi

Migration dosyasını `alembic/versions/` klasörüne ekleyin.

Dosyadaki Alembic kimliklerini mevcut migration zincirinize göre düzenleyin:

```python
revision = "yeni_revision_id"
down_revision = "bir_onceki_revision_id"
```

Migration'ı çalıştırmak için:

```bash
docker compose exec api alembic upgrade head
```

Compose dosyasındaki API başlangıç komutu zaten migration çalıştırıyorsa:

```yaml
command: sh -c "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"
```

image yeniden oluşturulup API yeniden başlatıldığında migration otomatik uygulanır:

```bash
docker compose up -d --build api
```

Migration eski `vector(384)` embeddingleri koruyamaz. Soru-cevap kayıtları korunur ancak embedding alanları yeniden üretilmelidir:

```bash
docker compose exec api python scripts/qa_crud.py reembed --all
```

## 6. Komutların genel kullanımı

API container'ı çalışıyorsa komutlar şu formatta çalıştırılır:

```bash
docker compose exec api python scripts/qa_crud.py KOMUT PARAMETRELER
```

Container adı üzerinden de çalıştırılabilir:

```bash
docker exec -it bfl_api python scripts/qa_crud.py KOMUT PARAMETRELER
```

Önerilen kullanım `docker compose exec api` biçimidir.

Yardım ekranı:

```bash
docker compose exec api python scripts/qa_crud.py --help
```

Belirli bir komutun yardım ekranı:

```bash
docker compose exec api python scripts/qa_crud.py create --help
```

## 7. Yeni kayıt ekleme

Yeni bir soru-cevap kaydı eklemek için:

```bash
docker compose exec api python scripts/qa_crud.py create \
  --question "Büyük Filo ne iş yapıyor?" \
  --answer "Büyük Filo kurumsal müşterilere uzun dönem araç kiralama ve filo yönetimi hizmetleri sunar." \
  --intent "hakkimizda"
```

Kayıt oluşturulurken:

1. Soru metni `BAAI/bge-m3` ile vektörleştirilir.
2. 1024 boyutlu embedding üretilir.
3. Soru, cevap, intent ve embedding aynı transaction içinde veritabanına yazılır.
4. Aynı soru daha önce eklenmişse işlem durdurulur.

### Augmented kayıt ekleme

```bash
docker compose exec api python scripts/qa_crud.py create \
  --question "Firmanız hangi filo hizmetlerini sağlıyor?" \
  --answer "Uzun dönem araç kiralama ve uçtan uca filo yönetimi hizmetleri sunuyoruz." \
  --intent "hakkimizda" \
  --augmented
```

### Aynı sorunun tekrar eklenmesine izin verme

Normalde aynı soru ikinci kez eklenmez. Bilinçli olarak duplicate kayıt oluşturmak için:

```bash
docker compose exec api python scripts/qa_crud.py create \
  --question "Büyük Filo nedir?" \
  --answer "Büyük Filo bir operasyonel araç kiralama şirketidir." \
  --intent "hakkimizda" \
  --allow-duplicate
```

## 8. Kayıtları listeleme

Son 50 kaydı listelemek için:

```bash
docker compose exec api python scripts/qa_crud.py list
```

Listeleme sonucu JSON formatında döner.

### Kayıt sayısını sınırlama

```bash
docker compose exec api python scripts/qa_crud.py list --limit 20
```

### Sayfalama

İlk 20 kaydı atlayıp sonraki 20 kaydı getirmek için:

```bash
docker compose exec api python scripts/qa_crud.py list \
  --limit 20 \
  --offset 20
```

### Intent kategorisine göre filtreleme

```bash
docker compose exec api python scripts/qa_crud.py list \
  --intent "ariza" \
  --limit 50
```

### Augmented kayıtları filtreleme

Sadece augmented kayıtlar:

```bash
docker compose exec api python scripts/qa_crud.py list \
  --augmented true
```

Sadece normal kayıtlar:

```bash
docker compose exec api python scripts/qa_crud.py list \
  --augmented false
```

### Soru veya cevap içinde metin arama

```bash
docker compose exec api python scripts/qa_crud.py list \
  --text "lastik"
```

Filtreler birlikte kullanılabilir:

```bash
docker compose exec api python scripts/qa_crud.py list \
  --intent "ariza" \
  --augmented false \
  --text "yardım" \
  --limit 20
```

## 9. ID ile tek kayıt getirme

```bash
docker compose exec api python scripts/qa_crud.py get --id 1692
```

Örnek çıktı:

```json
{
  "id": 1692,
  "question": "Büyük Filo ne iş yapıyor?",
  "answer": "Büyük Filo kurumsal müşterilere filo kiralama hizmeti sunar.",
  "intent_category": "hakkimizda",
  "is_augmented": false,
  "created_at": "2026-07-01T13:09:06+00:00",
  "has_embedding": true
}
```

`has_embedding` alanı kaydın embedding değerinin bulunup bulunmadığını gösterir.

## 10. Kayıt güncelleme

### Cevabı güncelleme

```bash
docker compose exec api python scripts/qa_crud.py update \
  --id 1692 \
  --answer "Büyük Filo, uzun dönem araç kiralama ve filo yönetimi hizmetleri sunmaktadır."
```

Yalnızca cevap değiştiğinde embedding yeniden üretilmez; çünkü embedding soru metninden oluşturulur.

### Soruyu güncelleme

```bash
docker compose exec api python scripts/qa_crud.py update \
  --id 1692 \
  --question "Büyük Filo hangi hizmetleri sunuyor?"
```

Soru değiştirildiğinde embedding otomatik olarak yeniden oluşturulur.

### Intent kategorisini güncelleme

```bash
docker compose exec api python scripts/qa_crud.py update \
  --id 1692 \
  --intent "genel_bilgi"
```

### Augmented durumunu güncelleme

```bash
docker compose exec api python scripts/qa_crud.py update \
  --id 1692 \
  --augmented true
```

Tekrar normal kayıt yapmak için:

```bash
docker compose exec api python scripts/qa_crud.py update \
  --id 1692 \
  --augmented false
```

### Birden fazla alanı aynı anda güncelleme

```bash
docker compose exec api python scripts/qa_crud.py update \
  --id 1692 \
  --question "Büyük Filo hangi alanlarda hizmet veriyor?" \
  --answer "Kurumsal araç kiralama, filo yönetimi ve mobilite çözümleri sunmaktadır." \
  --intent "hakkimizda" \
  --augmented false
```

## 11. Kayıt silme

```bash
docker compose exec api python scripts/qa_crud.py delete --id 1692
```

Başarılı işlem örneği:

```json
{
  "deleted": true,
  "record": {
    "id": 1692,
    "question": "Büyük Filo ne iş yapıyor?"
  }
}
```

> Silme işlemi kalıcıdır. Özellikle toplu değişikliklerden önce PostgreSQL yedeği alınması önerilir.

## 12. Semantik arama

Kullanıcı cümlesine en yakın soruları bulmak için:

```bash
docker compose exec api python scripts/qa_crud.py search \
  --query "Yolda kaldım ve aracım çalışmıyor" \
  --limit 5
```

Arama sırasında:

1. Girilen sorgu `BAAI/bge-m3` ile vektörleştirilir.
2. PostgreSQL pgvector cosine distance operatörü kullanılır.
3. En yakın kayıtlar benzerlik değerine göre sıralanır.

Kullanılan benzerlik hesabı:

```sql
1 - (embedding <=> query_embedding)
```

Örnek çıktı:

```json
[
  {
    "id": 12,
    "question": "Araç çalışmıyor ne yapacağım",
    "answer": "Araç arızası için 7/24 acil hattımızı arayabilirsiniz.",
    "intent_category": "ariza",
    "is_augmented": false,
    "similarity": 0.91
  }
]
```

### Intent içinde semantik arama

```bash
docker compose exec api python scripts/qa_crud.py search \
  --query "Aracımla yolda kaldım" \
  --intent "ariza" \
  --limit 5
```

## 13. Embeddingleri yeniden oluşturma

Model değiştirildiğinde, embedding kolon boyutu değiştirildiğinde veya embedding alanları boş kaldığında kayıtlar yeniden vektörleştirilmelidir.

### Tüm kayıtları yeniden vektörleştirme

```bash
docker compose exec api python scripts/qa_crud.py reembed --all
```

### Tek kaydı yeniden vektörleştirme

```bash
docker compose exec api python scripts/qa_crud.py reembed --id 1692
```

### Batch boyutunu değiştirme

```bash
docker compose exec api python scripts/qa_crud.py reembed \
  --all \
  --batch-size 16
```

GPU belleği veya sistem belleği yetersizse batch boyutu düşürülebilir:

```bash
docker compose exec api python scripts/qa_crud.py reembed \
  --all \
  --batch-size 8
```

## 14. Hugging Face model cache'i

Compose dosyasında aşağıdaki yapı bulunmaktadır:

```yaml
environment:
  HF_HOME: /models

volumes:
  - hf_models:/models
```

Bu nedenle `BAAI/bge-m3` modeli ilk kullanımda `/models` dizinine indirilir ve `hf_models` volume'ünde kalıcı olarak saklanır.

Modelin her container yeniden başlatıldığında tekrar indirilmesi gerekmez.

Volume durumunu görmek için:

```bash
docker volume ls | grep hf_models
```

Model cache'ini silmek için:

```bash
docker compose down
docker volume rm PROJEADI_hf_models
```

> Cache silinirse model bir sonraki embedding işleminde yeniden indirilir.

## 15. API çalışmıyorsa tek seferlik komut çalıştırma

API container'ı çalışmıyorsa geçici container ile komut çalıştırılabilir:

```bash
docker compose run --rm api python scripts/qa_crud.py list
```

Tüm kayıtları yeniden vektörleştirme örneği:

```bash
docker compose run --rm api python scripts/qa_crud.py reembed --all
```

Normal kullanımda çalışan API container'ı üzerinde `docker compose exec` tercih edilmelidir.

## 16. Veritabanını doğrudan kontrol etme

PostgreSQL container'ına bağlanmak için:

```bash
docker compose exec postgres psql \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB"
```

Environment değişkenleri shell ortamında yoksa doğrudan değer verilebilir:

```bash
docker compose exec postgres psql -U postgres -d postgres
```

Tablo yapısını kontrol etmek için:

```sql
\d+ qa_embeddings
```

Embedding kolon tipini kontrol etmek için:

```sql
SELECT
    column_name,
    data_type,
    udt_name
FROM information_schema.columns
WHERE table_name = 'qa_embeddings';
```

pgvector'a özel kesin kolon tipini görmek için:

```sql
SELECT
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS column_type
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname = 'qa_embeddings'
  AND a.attname = 'embedding'
  AND a.attnum > 0
  AND NOT a.attisdropped;
```

Beklenen sonuç:

```text
embedding | vector(1024)
```

Kayıt sayılarını intent bazında görmek için:

```sql
SELECT
    intent_category,
    COUNT(*) AS record_count
FROM qa_embeddings
GROUP BY intent_category
ORDER BY record_count DESC;
```

Embeddingi olmayan kayıtları görmek için:

```sql
SELECT id, question, intent_category
FROM qa_embeddings
WHERE embedding IS NULL
ORDER BY id;
```

## 17. Önerilen ilk kurulum sırası

Yeni script ve migration projeye eklendikten sonra aşağıdaki sıra kullanılabilir:

```bash
# 1. API image'ını yeniden oluştur ve servisleri başlat
docker compose up -d --build

# 2. Servislerin durumunu kontrol et
docker compose ps

# 3. Migration durumunu kontrol et
docker compose exec api alembic current

# 4. Son migration'a geç
docker compose exec api alembic upgrade head

# 5. Mevcut kayıtları BGE-M3 ile yeniden vektörleştir
docker compose exec api python scripts/qa_crud.py reembed --all

# 6. Kayıtları listele
docker compose exec api python scripts/qa_crud.py list --limit 10

# 7. Semantik aramayı test et
docker compose exec api python scripts/qa_crud.py search \
  --query "Aracım bozuldu ne yapmalıyım?" \
  --limit 5
```

## 18. Sık karşılaşılan hatalar

### `expected 1024 dimensions, not 384`

Neden:

- Model 1024 boyutlu embedding üretiyor.
- Veritabanı kolonu hâlâ `vector(384)`.

Çözüm:

```bash
docker compose exec api alembic upgrade head
docker compose exec api python scripts/qa_crud.py reembed --all
```

### `connection refused` veya PostgreSQL bağlantı hatası

Container içindeki `.env` ayarlarını kontrol edin:

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

Container içinden `localhost:5438` kullanılmamalıdır.

### `No such file or directory: scripts/qa_crud.py`

Prod ortamında bind mount kapalı olduğu için script image içinde bulunmuyor olabilir.

Çözüm:

```bash
docker compose up -d --build api
```

Dosyanın container içinde olup olmadığını kontrol edin:

```bash
docker compose exec api ls -la /app/scripts
```

### `ModuleNotFoundError: No module named app`

Compose ortamında aşağıdaki değer bulunmalıdır:

```yaml
environment:
  PYTHONPATH: /app
```

Ayrıca Dockerfile çalışma dizini `/app` olmalıdır:

```dockerfile
WORKDIR /app
```

### Model her seferinde tekrar indiriliyor

Aşağıdaki volume ve environment ayarlarının bulunduğunu kontrol edin:

```yaml
environment:
  HF_HOME: /models
volumes:
  - hf_models:/models
```

### Embedding oluşturma sırasında container kapanıyor

Muhtemel neden bellek yetersizliğidir. Batch boyutunu düşürün:

```bash
docker compose exec api python scripts/qa_crud.py reembed \
  --all \
  --batch-size 8
```

Container loglarını kontrol edin:

```bash
docker compose logs --tail=200 api
```

## 19. Seed scripti ile ilgili önemli uyarı

Eski seed scriptinde aşağıdaki sorgu varsa:

```sql
DELETE FROM qa_embeddings WHERE is_augmented = FALSE;
```

seed scripti tekrar çalıştırıldığında CRUD aracıyla manuel eklenen bütün normal kayıtlar da silinir.

Bu nedenle toplu silme yerine soru bazlı `INSERT` veya `UPDATE` yaklaşımı kullanılmalıdır. Mümkünse veritabanında soru için unique alan veya ayrı bir `source_key` alanı tanımlanmalıdır.

Önerilen uzun vadeli alanlar:

```sql
ALTER TABLE qa_embeddings
ADD COLUMN source_key VARCHAR(128),
ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
```

Seed kayıtları `source_key` üzerinden güncellenebilir; kullanıcı tarafından oluşturulan kayıtlar etkilenmez.

## 20. Komut özeti

| İşlem | Komut |
|---|---|
| Yeni kayıt | `create` |
| Listeleme | `list` |
| Tek kayıt | `get --id ID` |
| Güncelleme | `update --id ID` |
| Silme | `delete --id ID` |
| Semantik arama | `search --query METIN` |
| Tüm embeddingleri yenileme | `reembed --all` |
| Tek embeddingi yenileme | `reembed --id ID` |

Tüm komutlar Docker içinde aşağıdaki temel formatla çalıştırılır:

```bash
docker compose exec api python scripts/qa_crud.py ...
```
