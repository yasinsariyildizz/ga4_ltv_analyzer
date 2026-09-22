# GA4 LTV Toolkit — Türkçe Analiz ve Yorumlama Rehberi

Bu doküman, `ga4-ltv-toolkit` içindeki gözlemlenmiş müşteri yaşam boyu değeri analizinin çalışma mantığını, üretilen tabloları, grafiklerin nasıl okunacağını ve sonuçların hangi sınırlar içinde yorumlanması gerektiğini açıklar.

Amaç yalnızca kodu çalıştırmak değildir. Asıl amaç aşağıdaki sorulara tutarlı cevap vermektir:

- Kimliği belirlenebilen müşteriler bugüne kadar ne kadar net satın alma geliri oluşturdu?
- Ortalama müşteri değeri ile tipik müşteri değeri arasında fark var mı?
- Gelir az sayıdaki yüksek değerli müşteride mi toplanıyor?
- Tekrar satın alma davranışı ne kadar güçlü?
- Aylık e-ticaret performansı nasıl değişiyor?
- ARPU, ARPPU, AOV ve dönüşüm göstergeleri MoM ve YoY olarak nasıl ilerliyor?
- İlk satın alma aylarına göre temel müşteri grupları nasıl görünüyor?

Bu analiz **gelecekteki LTV'yi tahmin etmez**. Yalnızca seçilen GA4 geçmişinde gerçekten görülen satın alma ve iade kayıtlarından gözlemlenmiş gelir LTV'si hesaplar.

---

# 1. Analizin kısa tanımı

Müşteri bazındaki temel hesap şöyledir:

```text
Gözlemlenmiş LTV = toplam satın alma geliri − toplam iade tutarı
```

Örnek:

```text
1. sipariş                 900 TL
2. sipariş                 600 TL
İade                       200 TL
--------------------------------
Gözlemlenmiş LTV          1.300 TL
```

Bu değer, müşterinin gelecekte yapacağı alışverişleri içermez. Analizdeki “yaşam boyu” ifadesi, seçilen veri geçmişinde gözlemlenebilen süreyi anlatır.

---

# 2. Bu analiz ne değildir?

Bu çalışma aşağıdaki analizlerle karıştırılmamalıdır:

- Gelecek 6 veya 12 aylık LTV tahmini değildir.
- Kâr LTV'si değildir.
- Müşteri edinme maliyetini içermez.
- Kampanya katkısını tek başına ölçmez.
- Ayrıntılı retention veya eşit yaşta kohort analizi değildir.
- Müşterileri otomatik olarak iyi, kötü veya kaybedilecek şeklinde sınıflandırmaz.

Ürün maliyeti, kargo, komisyon, reklam harcaması ve müşteri hizmetleri maliyeti bulunmadığı için sonuç **gelir bazlı LTV** olarak okunmalıdır.

---

# 3. Analizde hangi kullanıcı kimliği kullanılır?

Müşteri LTV'si **`user_id` bazında** hesaplanır.

`user_pseudo_id` çoğunlukla tarayıcı veya cihaz kimliğidir. Aynı kişi telefon, bilgisayar ve farklı tarayıcılarla geldiğinde birden fazla kullanıcı gibi görünebilir. `user_id` doğru uygulanmışsa giriş yapan müşteriyi cihazlar arasında bir araya getirebilir.

## `user_id` kullanımının avantajı

- Analiz kişi veya müşteri hesabına daha yakın bir düzeyde yapılır.
- Aynı müşterinin farklı cihazlardaki alışverişleri birleştirilebilir.
- Sipariş sıklığı ve tekrar satın alma oranı daha anlamlı olur.

## Dikkat edilmesi gereken nokta

`user_id` boş olan satın almalar müşteri LTV'sine katılmaz. Bu nedenle sonuç bütün satın alanları değil, kimliği belirlenebilen satın alanları temsil eder.

Paket bu kaybı saklamaz. `ltv_data_quality` tablosunda şu oranı üretir:

```text
user_id kapsamı = user_id bulunan satın alma / bütün satın alma olayları
```

Örneğin kapsam %62 ise müşteri LTV'si satın almaların yaklaşık %62'si üzerinden hesaplanıyordur. Böyle bir durumda sonuçlar kullanılabilir; ancak “tüm müşteri tabanının LTV'si” şeklinde sunulmamalıdır.

---

# 4. Aylık metriklerde kullanıcı kapsamı neden farklıdır?

Aylık dijital performans katmanı yalnızca giriş yapan müşterileri değil, site veya uygulama trafiğinin daha geniş bölümünü kapsar.

Bu katmanda kullanıcı anahtarı şöyledir:

```text
user_id varsa          → user_id
user_id yoksa          → user_pseudo_id
```

Bu nedenle aşağıdaki iki sayı birebir aynı olmak zorunda değildir:

- `ltv_customer_summary` içindeki müşteri sayısı
- `ltv_monthly_metrics` içindeki aylık satın alan kullanıcı sayısı

İlk sayı yalnızca `user_id` ile tanımlanan müşterileri, ikinci sayı ise mümkün olduğunda `user_id`, aksi durumda cihaz/tarayıcı kimliğini kullanır.

Google Signals ve davranış modelleme BigQuery dışa aktarımında yer almadığı için aylık kullanıcı sayıları GA4 arayüzüyle de birebir eşleşmeyebilir.

---

# 5. Gerekli GA4 uygulaması

Analizin sağlıklı çalışması için en az aşağıdaki alanların düzenli gönderilmesi gerekir:

- `user_id`
- `user_pseudo_id`
- `event_name`
- `event_date`
- `event_timestamp`
- `ecommerce.transaction_id`
- `ecommerce.purchase_revenue`
- `ecommerce.purchase_revenue_in_usd`
- `ecommerce.refund_value`
- `ecommerce.refund_value_in_usd`
- `ecommerce.total_item_quantity`
- `ga_session_id`
- `session_engaged`

Aylık funnel göstergeleri için aşağıdaki standart e-ticaret olaylarının da doğru uygulanması gerekir:

```text
view_item
add_to_cart
begin_checkout
purchase
refund
```

Bir olay hiç gönderilmiyorsa ilgili oran teknik olarak hesaplanabilir görünse bile iş açısından anlamlı olmayabilir.

---

# 6. Dört giriş alanı

Modül yalnızca dört temel giriş kullanır:

```python
analysis = LTVAnalyzer(
    project_id="client-project-id",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_ltv",
)
```

| Alan | Açıklama |
| --- | --- |
| `project_id` | GA4 tablolarının bulunduğu Google Cloud projesi |
| `dataset_id` | GA4 veri kümesi; örneğin `analytics_123456789` |
| `table_id` | Genellikle `events_*` |
| `output_dataset_id` | Sonuç tablolarının yazılacağı veri kümesi |

LTV eşiği, tahmin süresi, müşteri sınıfı veya para birimi gibi ek bir giriş istenmez.

---

# 7. Önerilen çalışma sırası

```python
analysis.validate()
analysis.dry_run()
analysis.create_base_table()
analysis.ltv_analysis()
analysis.monthly_metrics_analysis()
analysis.cohort_analysis()
dashboard_path = analysis.generate_dashboard()
```

Adımların sırası önemlidir. Örneğin `ltv_analysis()` çalışmadan önce müşteri temel tabloları bulunmaz; `generate_dashboard()` çalışmadan önce de LTV, aylık metrik ve temel kohort tablolarının hazırlanmış olması gerekir.

Tüm akışı tek seferde çalıştırmak için:

```python
results = analysis.run_all()
```

İlk denemede adımları tek tek çalıştırmak daha uygundur. Böylece veri kalitesi ve tahmini tarama miktarı sonuç tabloları oluşturulmadan önce incelenebilir.

---

# 8. `validate()` — bağlantı ve tablo kontrolü

`validate()` kaynak veri kümesine erişimi ve verilen tablo deseninin eşleşip eşleşmediğini kontrol eder.

Bu adım:

- BigQuery bağlantısını doğrular,
- kaynak veri kümesinin bölgesini gösterir,
- `events_*` deseniyle kaç tablo eşleştiğini sayar,
- çıktı veri kümesinin adını bildirir,
- henüz analiz tablosu yazmaz.

Eşleşen tablo sayısı beklenenden çok düşükse yanlış veri kümesi veya yanlış tablo deseni seçilmiş olabilir.

---

# 9. `dry_run()` — maliyet ön kontrolü

`dry_run()` hiçbir tablo yazmadan ham GA4 verisinin yaklaşık ne kadar taranacağını gösterir.

Modülde iki ayrı ham veri taraması vardır:

1. Satın alma ve iade temel tablosu
2. Aylık dijital ve e-ticaret metrikleri

Sonraki adımlar bu iki taramadan üretilen küçük sonuç tablolarını kullanır.

## Örnek yorum

```text
Tahmini toplam tarama: 38 GB
```

Bu sayı, sorgular gerçekten çalıştırıldığında taranması beklenen veriyi gösterir. Veri dönemi veya kaynak tablo deseni değişirse `dry_run()` yeniden çalıştırılmalıdır.

---

# 10. `create_base_table()` — satın alma ve iade tabanı

Bu adım iki tablo oluşturur:

```text
ltv_transaction_base
ltv_data_quality
```

`ltv_transaction_base` satır düzeyi şöyledir:

```text
bir tekilleştirilmiş purchase veya refund olayı
```

Günlük `events_YYYYMMDD` tabloları kullanılır. Aynı günün verisini tekrar saymamak için `events_intraday_*` tabloları kapsam dışında bırakılır.

---

# 11. Satın alma tekilleştirmesi nasıl yapılır?

Aynı satın alma olayının teknik nedenlerle birden fazla kez gönderilmesi sipariş ve geliri şişirebilir.

`transaction_id` bulunduğunda satın alma anahtarı temel olarak şu alanlardan oluşur:

```text
purchase + kullanıcı + transaction_id
```

Aynı anahtar birden fazla kez görülürse son sunucu kaydı tutulur.

`transaction_id` yoksa olay zamanı, kullanıcı ve olay paket sırası kullanılarak teknik bir yedek anahtar oluşturulur. Bu yöntem tekrarları azaltır; fakat doğru bir `transaction_id` kadar güvenilir değildir.

Bu nedenle `transaction_id_coverage_rate` mümkün olduğunca yüksek olmalıdır.

---

# 12. İadeler nasıl işlenir?

İade olayları satın alma gelirinden düşülür:

```text
Net gelir = brüt satın alma geliri − iade tutarı
```

Bir siparişe birden fazla kısmi iade gelebileceği için iadeler yalnızca `transaction_id` üzerinden tek satıra indirilmez. Olay zamanı ve iade tutarı da anahtara eklenir.

İade olayında müşteri kimliği eksikse iade ilgili `user_id` satırına bağlanamayabilir. Böyle bir durumda genel iade tutarı ile müşteri LTV toplamı arasında fark oluşabilir.

---

# 13. Veri kalitesi tablosu nasıl okunur?

`ltv_data_quality` tek satırlık bir kontrol tablosudur.

| Alan | Anlamı |
| --- | --- |
| `purchase_events` | Tekilleştirme sonrası satın alma olayları |
| `refund_events` | Tekilleştirme sonrası iade olayları |
| `eligible_purchase_events` | `user_id` bulunduğu için LTV'ye girebilen satın almalar |
| `purchase_events_missing_user_id` | Müşteriye bağlanamayan satın almalar |
| `purchase_events_missing_transaction_id` | İşlem kimliği eksik satın almalar |
| `purchase_events_missing_revenue` | Gelir alanı eksik satın almalar |
| `user_id_coverage_rate` | LTV kapsam oranı |
| `transaction_id_coverage_rate` | Tekilleştirme için işlem kimliği kapsamı |
| `revenue_coverage_rate` | Gelir alanı kapsamı |
| `distinct_purchase_currencies` | Görülen satın alma para birimi sayısı |

## Örnek değerlendirme

```text
user_id kapsamı          %81
transaction_id kapsamı  %98
gelir kapsamı            %99
```

Bu örnekte işlem ve gelir uygulaması güçlüdür. Ancak müşteri LTV'si satın almaların yaklaşık %81'ini temsil eder. Sunumda bu kapsam açıkça belirtilmelidir.

---

# 14. `ltv_analysis()` hangi tabloları üretir?

Bu adım aşağıdaki tabloları oluşturur:

```text
ltv_customer_summary
ltv_overall_summary
ltv_decile_summary
ltv_percentile_distribution
```

Notebook içinde ayrıca özet kartları, LTV dağılım grafikleri ve otomatik yorum notları gösterilir.

---

# 15. Müşteri özet tablosunun satır düzeyi

`ltv_customer_summary` tablosunda her satır bir `user_id` değerini temsil eder.

Başlıca alanlar:

- ilk satın alma tarihi,
- son satın alma tarihi,
- sipariş sayısı,
- iade olayı sayısı,
- tekrar satın alan müşteri bilgisi,
- ilk ve son satın alma arasındaki gün sayısı,
- ilk satın almadan analiz sonuna kadar gözlenen gün,
- son satın almadan analiz sonuna kadar geçen gün,
- brüt gelir,
- iade tutarı,
- net gelir,
- müşteri bazında AOV.

`repeat_customer = TRUE` olması müşterinin seçilen veri döneminde en az iki satın alma olayı bulunduğunu gösterir.

Analiz sonu, satın alma/iade temel tablosunda görülen en son olay tarihidir. Kaynak dönemin sonunda hiç ticaret olayı yoksa bu tarih en son ham GA4 tarihinden daha eski olabilir.

---

# 16. Ortalama ve ortanca LTV birlikte nasıl okunur?

## Ortalama LTV

```text
Ortalama LTV = toplam net gelir / müşteri sayısı
```

Ortalama, toplam müşteri tabanının ekonomik değerini özetlemek için kullanışlıdır. Ancak birkaç yüksek değerli müşteri ortalamayı belirgin biçimde yükseltebilir.

## Ortanca LTV

Müşteriler LTV'ye göre sıralandığında ortada kalan müşterinin değeridir.

Örnek:

```text
Ortalama LTV   2.450 TL
Ortanca LTV      820 TL
```

Bu sonuç “tipik” müşterinin yaklaşık 820 TL değer ürettiğini, az sayıdaki yüksek değerli müşterinin ortalamayı yukarı çektiğini düşündürür.

Ortalama ve ortancanın birbirine yakın olması ise müşteri değerlerinin daha dengeli dağıldığına işaret edebilir.

---

# 17. P75, P90 ve P95 nasıl yorumlanır?

Yüzdelikler müşteri değer dağılımının üst bölümünü anlamaya yardımcı olur.

```text
P75 = müşterilerin %75'i bu değerin altında veya bu değere eşittir
P90 = müşterilerin %90'ı bu değerin altında veya bu değere eşittir
P95 = müşterilerin %95'i bu değerin altında veya bu değere eşittir
```

Örnek:

```text
Ortanca   800 TL
P75     1.500 TL
P90     4.200 TL
P95     8.700 TL
```

P90 ile P95 arasındaki büyük fark, en yüksek değerli müşteri grubunda uzun bir kuyruk bulunduğunu gösterebilir.

Bu değerler doğrudan kampanya eşiği değildir. Müşteri sayısı, ürün marjı, tekrar alışveriş süresi ve iletişim maliyetiyle birlikte değerlendirilmelidir.

---

# 18. Negatif LTV ne anlama gelir?

Bir müşterinin net geliri sıfırın altındaysa seçilen veri döneminde müşteriye bağlanan iade tutarı satın alma gelirinden yüksektir.

Olası nedenler:

- önceki dönemdeki bir satın almanın iadesi mevcut dönemde görülmüştür,
- satın alma olayında `user_id` eksik, iade olayında doludur,
- iade iki kez gönderilmiştir,
- satın alma geliri eksik iletilmiştir,
- gerçekten satın alma tutarından yüksek düzeltme yapılmıştır.

Negatif LTV müşterileri otomatik olarak “zararlı müşteri” şeklinde etiketlenmemelidir. Önce olay uygulaması ve seçilen veri dönemi kontrol edilmelidir.

---

# 19. LTV dilimleri nasıl oluşturulur?

Müşteriler net gelirlerine göre yüksekten düşüğe sıralanır ve yaklaşık eşit büyüklükte on gruba ayrılır.

```text
D1  → en yüksek LTV'li yaklaşık ilk %10
D10 → en düşük LTV'li yaklaşık son %10
```

Her dilimde şu değerler bulunur:

- müşteri sayısı,
- sipariş sayısı,
- toplam ve ortalama net gelir,
- minimum ve maksimum LTV,
- tekrar satın alma oranı,
- pozitif net gelir payı,
- kümülatif müşteri ve gelir payı.

Müşteri sayısı 10'a tam bölünmediğinde dilimler birebir aynı büyüklükte olmayabilir.

---

# 20. Gelir yoğunlaşması nasıl yorumlanır?

Gelir yoğunlaşması grafiği en yüksek LTV'li müşterilerden başlayarak kümülatif pozitif net gelir payını gösterir.

Örnek:

```text
En yüksek LTV'li %10 müşteri → pozitif net gelirin %44'ü
En yüksek LTV'li %20 müşteri → pozitif net gelirin %63'ü
```

Bu sonuç müşteri değerinin üst grupta yoğunlaştığını gösterir.

Yorum:

- D1 ve D2 müşterileri için koruma ve deneyim çalışmaları önemli olabilir.
- Gelir birkaç müşteriye aşırı bağımlıysa kayıp riski daha yüksektir.
- Düşük dilimlerdeki müşteriler için ikinci siparişe geçiş fırsatı araştırılabilir.

Yoğunlaşma payında negatif LTV değerleri sıfır kabul edilir. Böylece negatif iadeler pozitif gelir dağılımını yapay biçimde bozmaz.

---

# 21. Tekrar satın alma oranı ve sipariş sıklığı

Müşteri seviyesindeki tekrar oranı:

```text
Tekrar satın alan müşteri oranı = en az iki sipariş veren müşteri / bütün LTV müşterileri
```

Müşteri başına sipariş:

```text
Sipariş / müşteri = toplam sipariş / bütün LTV müşterileri
```

Bu iki metrik birlikte okunmalıdır.

Örnek:

```text
Tekrar oranı          %18
Sipariş / müşteri     1,32
```

Müşterilerin küçük bir bölümü tekrar satın alıyor ve ortalama sipariş sayısı da düşük kalıyorsa ikinci siparişe geçiş önemli bir gelişim alanı olabilir.

Ancak ürün doğal olarak yıllık veya çok seyrek satın alınıyorsa düşük tekrar oranı tek başına olumsuz yorumlanmamalıdır.

---

# 22. `monthly_metrics_analysis()` ne üretir?

Bu adım iki tablo oluşturur:

```text
ltv_monthly_metrics
ltv_monthly_metric_changes
```

İlk tabloda her satır bir takvim ayıdır. İkinci tabloda her satır bir ay ve bir metrik birleşimidir.

Notebook içinde:

- son eksiksiz ayın özet kartları,
- aylık gelir ve verimlilik eğilimleri,
- dönüşüm ve tekrar satın alma grafikleri,
- MoM ve YoY karşılaştırma tablosu

gösterilir.

---

# 23. Aylık temel e-ticaret metrikleri

| Metrik | Hesap |
| --- | --- |
| Brüt satın alma geliri | Tekilleştirilmiş satın alma gelirlerinin toplamı |
| Net satın alma geliri | Brüt gelir − iade tutarı |
| Sipariş | Tekilleştirilmiş `purchase` sayısı |
| Satın alan kullanıcı | Ay içinde en az bir satın alma yapan kullanıcı |
| Satın alma sıklığı | Sipariş / satın alan kullanıcı |
| Sipariş başına ürün | Satın alınan ürün adedi / sipariş |
| Aylık tekrar satın alan oranı | Ay içinde en az iki sipariş veren / o ay satın alan |
| Yeni satın alan oranı | Seçilen geçmişte ilk kez satın alan / o ay satın alan |

“Yeni satın alan” ifadesi seçilen veri geçmişine göredir. Veri Ocak 2025'te başlıyorsa Ocak 2025'te görülen eski bir müşteri de sistem tarafından ilk kez görülmüş sayılabilir.

---

# 24. ARPU, ARPPU ve AOV

Bu paketteki tanımlar şöyledir:

```text
E-ticaret ARPU  = net satın alma geliri / aktif kullanıcı
E-ticaret ARPPU = net satın alma geliri / satın alan kullanıcı
AOV             = brüt satın alma geliri / sipariş
Net AOV         = net satın alma geliri / sipariş
```

## Sayısal örnek

```text
Aktif kullanıcı                 10.000
Satın alan kullanıcı               800
Sipariş                           1.000
Brüt satın alma geliri       1.300.000 TL
İade tutarı                    100.000 TL
Net satın alma geliri        1.200.000 TL
```

Hesaplar:

```text
E-ticaret ARPU       1.200.000 / 10.000 = 120 TL
E-ticaret ARPPU      1.200.000 / 800    = 1.500 TL
AOV                  1.300.000 / 1.000  = 1.300 TL
Net AOV              1.200.000 / 1.000  = 1.200 TL
```

E-ticaret ARPU ile GA4'ün standart toplam gelir ARPU metriği aynı değildir. Bu paket yalnızca net satın alma gelirini kullanır; reklam veya abonelik geliri gibi başka gelir türleri paya eklenmez.

---

# 25. ARPU ve ARPPU birlikte nasıl yorumlanır?

ARPU bütün aktif kullanıcı kitlesinin gelir üretme gücünü, ARPPU ise satın alan kullanıcıların ortalama net gelir katkısını gösterir.

Olası durumlar:

## ARPU artıyor, ARPPU sabit

Daha fazla aktif kullanıcı satın almaya geçiyor olabilir. Satın alan başına gelir değişmese bile satın alan oranı yükselmiş olabilir.

## ARPU sabit, ARPPU artıyor

Satın alanların sepet değeri veya sipariş sıklığı yükselirken satın alan oranı düşmüş olabilir.

## ARPU ve ARPPU birlikte düşüyor

AOV, sipariş sıklığı, satın alan oranı veya iade payı birlikte incelenmelidir.

ARPU değişimi tek başına kampanya başarısı olarak yorumlanmamalıdır.

---

# 26. Oturum ve etkileşim metrikleri

Başlıca formüller:

```text
Etkileşim oranı = etkileşimli oturum / bütün oturumlar
Hemen çıkma oranı = 1 − etkileşim oranı
Aktif kullanıcı başına oturum = oturum / aktif kullanıcı
Aktif kullanıcı başına olay = olay / aktif kullanıcı
Oturum başına gelir = net satın alma geliri / oturum
```

Oturum anahtarı `user_pseudo_id + ga_session_id` birleşiminden oluşturulur. Bu alanlardan biri eksikse ilgili olay oturum sayımına giremez.

Etkileşim oranı yükselirken oturum başına gelir düşüyorsa içerik tüketimi artmış fakat ticari verimlilik aynı yönde ilerlememiş olabilir.

---

# 27. Dönüşüm ve funnel göstergeleri

Paket aşağıdaki oranları üretir:

```text
Satın alan kullanıcı oranı = satın alan kullanıcı / aktif kullanıcı
Oturum satın alma oranı = satın alma olan oturum / bütün oturumlar
Ürün görüntülemeden sepete geçiş = add_to_cart kullanıcısı / view_item kullanıcısı
Sepetten ödeme başlangıcına geçiş = begin_checkout kullanıcısı / add_to_cart kullanıcısı
Ödeme başlangıcından satın almaya geçiş = purchase kullanıcısı / begin_checkout kullanıcısı
Ürün görüntülemeden satın almaya geçiş = purchase kullanıcısı / view_item kullanıcısı
```

Bu oranlar aynı takvim ayındaki tekil kullanıcıları karşılaştırır. Zorunlu sıralı, aynı oturumlu kapalı funnel analizi değildir.

Örneğin bir kullanıcı ürünü önceki ay görüntüleyip bu ay doğrudan satın alabilir. Bu nedenle bazı geçiş oranları gerçek yolculuk oranı gibi yorumlanmamalıdır. Ayrıntılı açık/kapalı funnel analizi ayrı bir modülün konusudur.

---

# 28. İade göstergeleri

```text
İade tutarı payı = iade tutarı / brüt satın alma geliri
Sipariş başına iade olayı = iade olayı / sipariş
```

İade tutarı payı finansal etkiyi, sipariş başına iade olayı ise olay sıklığını gösterir.

Bir iade olayı birden fazla ürün veya kısmi tutar içerebilir. Bu nedenle iki oran aynı şeyi ölçmez.

İade payı artarken brüt gelir sabit kalıyorsa net gelir, net AOV, ARPU ve LTV baskı altında kalabilir.

---

# 29. MoM nasıl hesaplanır?

MoM, bir eksiksiz takvim ayını bir önceki takvim ayıyla karşılaştırır.

```text
Mutlak değişim = mevcut ay − önceki ay
MoM % = (mevcut ay − önceki ay) / |önceki ay|
```

Örnek:

```text
Ocak net gelir   1.000.000 TL
Şubat net gelir  1.200.000 TL

Mutlak fark       +200.000 TL
MoM değişim             +%20
```

Ocak verisi yoksa Şubat başka bir mevcut aya bağlanmaz. Karşılaştırma boş bırakılır.

---

# 30. YoY nasıl hesaplanır?

YoY, bir ayı önceki yılın aynı ayıyla karşılaştırır.

```text
Şubat 2026 → Şubat 2025
```

Bu karşılaştırma mevsimselliği kısmen kontrol ettiği için özellikle moda, turizm, eğitim, hediye ve dönemsel kampanya işlerinde MoM'dan daha açıklayıcı olabilir.

Önceki yılın aynı ayı bulunmuyorsa YoY değişimi boş kalır. Sağlıklı YoY için en az 13 aylık veri geçmişi gerekir.

---

# 31. Oran metriklerinde yüzde ve yüzde puan farkı

Örnek:

```text
Önceki ay satın alma oranı  %2,0
Mevcut ay satın alma oranı  %2,5
```

İki farklı değişim vardır:

```text
Mutlak değişim   +0,5 yüzde puan
Göreli değişim   +%25
```

Rapor iki değeri de gösterir. “%0,5 arttı” ifadesi belirsizdir; “0,5 yüzde puan” veya “göreli olarak %25” şeklinde açıkça belirtilmelidir.

---

# 32. Eksiksiz ay kuralı

Aylık tabloda kısmi aylar saklanır; ancak kartlar, grafikler ve MoM/YoY hesapları mümkün olduğunda en güncel eksiksiz ayı kullanır.

Bir ay şu durumda eksiksiz kabul edilir:

```text
ayın ilk gününden son gününe kadar her takvim gününde en az bir dışa aktarılmış olay görülmesi
```

Örneğin veri 12 Eylül'de çalıştırıldıysa Eylül aylık tabloda bulunabilir; fakat Ağustos eksiksizse özet kartları Ağustos'u gösterir.

Bu yaklaşım 12 günlük Eylül verisini 31 günlük Ağustos verisiyle karşılaştırarak yapay düşüş üretilmesini önler.

---

# 33. Para birimi nasıl seçilir?

Paket kullanıcıdan ek para birimi seçimi istemez.

```text
Tek satın alma para birimi + yerel değer varsa → yerel gelir
Birden fazla para birimi varsa                → USD gelir
```

Hem yerel hem USD alanları BigQuery tablolarında tutulur. Grafik ve özet kartlarında uygun temel otomatik seçilir.

Birden fazla para birimini kur çevrimi yapmadan doğrudan toplamak yanlış olacağı için çoklu para biriminde USD alanına geçilir.

USD alanı eksikse çoklu para birimli sonuçlar dikkatle incelenmelidir.

---

# 34. `cohort_analysis()` — temel kohort özeti

Bu modüldeki kohort bölümü özellikle temel seviyede tutulmuştur.

Müşteriler ilk satın alma ayına göre gruplanır. Her grup için:

- müşteri sayısı,
- sipariş sayısı,
- ortalama gözlem süresi,
- brüt, iade ve net gelir,
- ortalama ve ortanca gözlemlenmiş LTV,
- müşteri başına sipariş,
- tekrar satın alma oranı,
- AOV,
- iade payı

hesaplanır.

Çıktı tablosunun satır düzeyi şöyledir:

```text
bir ilk satın alma ayı
```

---

# 35. Temel kohortlar neden doğrudan karşılaştırılmamalıdır?

Ocak ayında ilk kez satın alan müşteriler ile geçen ay ilk kez satın alan müşterilerin alışveriş için sahip olduğu süre aynı değildir.

Örnek:

```text
Ocak kohortu ortalama gözlem süresi   330 gün
Kasım kohortu ortalama gözlem süresi   40 gün
```

Ocak kohortunun daha yüksek LTV göstermesi yalnızca daha uzun süredir gözlenmesinden kaynaklanabilir.

Bu nedenle temel kohort tablosu:

- grup büyüklüğünü,
- ilk satın alma aylarının genel kalitesini,
- tekrar oranlarını,
- gözlem süresi farkını

görmek için kullanılır.

Ay-0, ay-1, ay-2 retention, eşit yaşta kümülatif LTV ve cohort matrisi ayrı kohort analizi modülünde ele alınmalıdır.

---

# 36. Grafikler nasıl okunmalıdır?

## LTV dilimlerine göre net gelir

D1'den D10'a doğru toplam net gelirin nasıl dağıldığını gösterir. İlk dilimler çok yüksekse müşteri değerinde yoğunlaşma vardır.

## Kümülatif pozitif gelir eğrisi

En yüksek LTV'li müşterilerden başlayarak müşteri payı ile gelir payı arasındaki ilişkiyi gösterir. Eşitlik çizgisinden güçlü sapma yoğunlaşmaya işaret eder.

## Aylık net satın alma geliri

Gelir trendini gösterir. Fiyat, trafik, satın alan oranı, AOV, sipariş sıklığı ve iadeler birlikte etkiler.

## ARPU ve ARPPU

Aktif kullanıcı kitlesinin ve satın alan kitlenin gelir verimliliğini birlikte gösterir.

## AOV ve oturum başına gelir

Sipariş değeri ile trafik değerini karşılaştırır. AOV artarken oturum başına gelir düşüyorsa satın alma oranı gerilemiş olabilir.

## Oturum satın alma ve tekrar satın alan oranı

Yeni dönüşüm performansı ile mevcut müşterilerin aylık tekrar davranışını yan yana gösterir.

## Temel kohort grafikleri

İlk satın alma ayına göre müşteri sayısı ile ortalama/ortanca gözlemlenmiş LTV'yi gösterir. Gözlem süresi farkı unutulmamalıdır.

---

# 37. HTML rapor nasıl kullanılmalıdır?

```python
dashboard_path = analysis.generate_dashboard("ga4_ltv_dashboard.html")
```

Rapor tek bir HTML dosyasıdır. Grafikler dosyanın içine gömülür; ayrıca resim klasörü taşımaz.

Raporda şu bölümler bulunur:

- genel LTV kartları,
- öne çıkan analiz notları,
- LTV dağılımı ve gelir yoğunlaşması,
- son eksiksiz ayın e-ticaret göstergeleri,
- aylık eğilim grafikleri,
- MoM ve YoY tablosu,
- temel kohort grafikleri,
- LTV dilim tablosu,
- veri kalitesi kontrolleri.

HTML rapor müşteri seviyesinde `user_id` listesi göstermez. Yine de gerçek marka sonuçları şirketin veri paylaşım kurallarına uygun ortamda tutulmalıdır.

---

# 38. Analiz hangi durumlarda yanıltıcı olabilir?

## `user_id` kapsamı düşükse

Sonuç tüm satın alanları temsil etmeyebilir.

## Veri geçmişi kısaysa

Tekrar satın alma oranı ve gözlemlenmiş LTV doğal olarak düşük kalabilir.

## `transaction_id` eksikse

Aynı siparişin tekrar gönderilmesi sipariş ve geliri şişirebilir.

## İadeler eksikse

Net gelir, net AOV ve LTV olduğundan yüksek görünebilir.

## İadeler müşteriye bağlanamıyorsa

Genel net gelir ile müşteri LTV toplamı farklılaşabilir.

## Para birimi uygulaması hatalıysa

Farklı para birimleri aynı tutarmış gibi toplanabilir veya USD alanı eksik kalabilir.

## Seçilen dönem kampanya ağırlıklıysa

AOV, ARPU ve satın alan oranı olağan dönemi temsil etmeyebilir.

## Kısmi ay karşılaştırılırsa

MoM ve YoY yapay düşüş gösterebilir. Modül bunu azaltmak için eksiksiz ay kuralını uygular.

## Temel kohortlar eşit yaşta sanılırsa

Eski kohortların daha uzun gözlem süresi yanlış biçimde “daha kaliteli müşteri” sonucu doğurabilir.

---

# 39. Bu dört girişle hesaplanamayan metrikler

Yalnızca GA4 olay tabloları kullanıldığında aşağıdaki metrikler güvenilir biçimde hesaplanamaz:

```text
ROAS
CPA
CAC
CPC
CPM
kâr LTV'si
LTV / CAC
katkı payı
ürün marjı
```

Bunlar için reklam maliyeti, ürün maliyeti, komisyon veya CRM/finans tablosu gibi ek kaynaklar gerekir.

Paket eksik maliyeti sıfır kabul edip yanıltıcı bir oran üretmez.

---

# 40. Sonuçların yönetime sunulması için örnek

```text
Analiz, seçilen GA4 döneminde user_id ile tanımlanabilen 42.600 satın alan müşteriyi kapsıyor.
Satın alma olaylarında user_id kapsamı %79, transaction_id kapsamı %98 ve gelir kapsamı %99.

Gözlemlenmiş ortalama LTV 2.180 TL, ortanca LTV 760 TL. Ortalama ile ortanca arasındaki fark, gelirin yüksek değerli küçük bir müşteri grubunda yoğunlaştığını gösteriyor. En yüksek LTV'li ilk %10 müşteri pozitif net gelirin %41'ini oluşturuyor.

Son eksiksiz ayda e-ticaret ARPU 126 TL, ARPPU 1.580 TL ve AOV 1.340 TL. Net gelir MoM %8 artarken satın alan kullanıcı oranı 0,3 yüzde puan geriledi. Büyüme daha çok sipariş değeri ve satın alan başına gelirden geliyor.

Temel kohort sonuçları ilk satın alma aylarına göre farklılık gösteriyor; ancak eski kohortların daha uzun gözlem süresi olduğu için bu farklar eşit yaşta performans farkı olarak yorumlanmamalı.
```

Bu sunum biçimi hem sonucu hem de veri kapsamını aynı anda gösterir.

---

# 41. Analiz öncesi kontrol listesi

- [ ] Doğru Google Cloud projesi ve GA4 veri kümesi seçildi mi?
- [ ] `events_*` günlük tabloları yeterli geçmişi kapsıyor mu?
- [ ] `user_id` uygulaması düzenli mi?
- [ ] `transaction_id` her satın almada gönderiliyor mu?
- [ ] Satın alma geliri ve para birimi doğru mu?
- [ ] İade olayları ve tutarları gönderiliyor mu?
- [ ] `ga_session_id` ve `session_engaged` alanları kullanılabilir mi?
- [ ] Standart e-ticaret olayları doğru adlarla gönderiliyor mu?
- [ ] `dry_run()` sonucu incelendi mi?

---

# 42. Analiz sonrası kontrol listesi

- [ ] `user_id` kapsam oranı rapora eklendi mi?
- [ ] Ortalama ve ortanca LTV birlikte yorumlandı mı?
- [ ] P90/P95 ve üst müşteri dilimleri kontrol edildi mi?
- [ ] Negatif LTV müşterileri veri uygulaması açısından incelendi mi?
- [ ] İade payı brüt ve net gelirle birlikte okundu mu?
- [ ] Aylık kartların hangi ayı gösterdiği kontrol edildi mi?
- [ ] MoM ve YoY karşılaştırma ayları eksiksiz mi?
- [ ] Oran farkları yüzde puan olarak doğru ifade edildi mi?
- [ ] Yeni satın alan metriğinin seçilen veri geçmişine bağlı olduğu belirtildi mi?
- [ ] Temel kohortlar gözlem süresi farkıyla birlikte yorumlandı mı?
- [ ] Sonuçların gelir LTV'si olduğu, kâr LTV'si olmadığı belirtildi mi?

---

# 43. Kısa özet

Bu modül, GA4 BigQuery dışa aktarımından `user_id` bazında gözlemlenmiş gelir LTV'si üretir. Satın alma ve iadeleri tekilleştirir, veri kapsamını ayrı gösterir, ortalama/ortanca/yüzdelik değerleri hesaplar ve müşteri değerinin ne kadar yoğunlaştığını açıklar.

Aylık katman; ARPU, ARPPU, AOV, net AOV, oturum başına gelir, satın alma sıklığı, dönüşüm, tekrar satın alma ve iade göstergelerini üretir. MoM ve YoY hesapları gerçek takvim aylarına bağlanır ve kısmi aylar karşılaştırmadan çıkarılır.

Kohort bölümü bilinçli olarak temel seviyededir. İlk satın alma ayına göre genel görünüm verir; eşit müşteri yaşında ayrıntılı kohort analizi yapmaz.

Sonuçların güvenilirliği en çok `user_id`, `transaction_id`, gelir, iade, oturum ve standart e-ticaret olaylarının uygulama kalitesine bağlıdır.
