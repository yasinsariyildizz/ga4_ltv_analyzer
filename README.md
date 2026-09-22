# GA4 LTV Toolkit

GA4 BigQuery dışa aktarımından, `user_id` bazında **gözlemlenmiş müşteri yaşam boyu değeri (LTV)** hesaplayan Python paketidir. Normal Google Colab üzerinde çalışır; BigQuery Notebook veya BigQuery Unified API gerektirmez.

Bu sürümde eşik değeri yoktur. Tahmin modeli, geleceğe yönelik süre seçimi ve elle girilen müşteri sınıfı kullanılmaz. Hesaplama doğrudan satın alma ve iade kayıtlarına dayanır.

## Dokümantasyon

- [Türkçe analiz ve yorumlama rehberi](docs/ANALYSIS_GUIDE_TR.md)
- [English analysis and interpretation guide](docs/ANALYSIS_GUIDE_EN.md)
- [English README](README_EN.md)

Rehberler yalnızca kurulum adımlarını değil; ortalama ve ortanca LTV'nin birlikte okunmasını, P75/P90/P95 değerlerini, gelir yoğunlaşmasını, ARPU/ARPPU/AOV ilişkisini, MoM ve YoY hesaplarını, kısmi ay kontrolünü, temel kohortların sınırlarını ve sonuçların yönetime nasıl aktarılacağını da açıklar.

## Dört giriş alanı

```python
from ga4_ltv import LTVAnalyzer

analysis = LTVAnalyzer(
    project_id="client-project-id",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_ltv",
)
```

| Alan | Ne yazılır? |
| --- | --- |
| `project_id` | GA4 tablolarının bulunduğu Google Cloud proje kimliği |
| `dataset_id` | GA4 veri kümesi; örneğin `analytics_123456789` |
| `table_id` | Genellikle `events_*` |
| `output_dataset_id` | Sonuç tablolarının yazılacağı veri kümesi; örneğin `ga4_ltv` |

## Çalıştırma sırası

```python
analysis.validate()
analysis.dry_run()
analysis.create_base_table()
analysis.ltv_analysis()
analysis.monthly_metrics_analysis()
analysis.cohort_analysis()
dashboard_path = analysis.generate_dashboard()
```

`dry_run()` hiçbir tablo yazmaz. Satın alma tabanı ile aylık performans katmanının iki ayrı GA4 taramasını adım adım ve toplam olarak gösterir.

## Ne hesaplanır?

- Her `user_id` için ilk ve son satın alma tarihi
- Sipariş sayısı ve müşteri başına sipariş
- Brüt gelir, iade ve net gelir
- Ortalama ve ortanca gözlemlenmiş LTV
- %75, %90 ve %95 LTV değerleri
- Tekrar satın alan müşteri oranı
- LTV dilimleri ve gelir yoğunlaşması
- Aylık ARPU, ARPPU, AOV, oturum başına gelir ve satın alma sıklığı
- Aktif kullanıcı, oturum, etkileşim ve satın alan kullanıcı oranları
- Ürün görüntüleme → sepete ekleme → ödeme başlangıcı → satın alma ilerleme oranları
- Aylık tekrar satın alan, yeni satın alan ve iade oranları
- Her metrik için aydan aya (MoM) ve yıldan yıla (YoY) değişim
- İlk satın alma ayına göre temel kohort özeti
- `user_id`, `transaction_id` ve gelir alanlarının doluluk kontrolü

## Oluşan BigQuery tabloları

| Tablo | Satır düzeyi | Amaç |
| --- | --- | --- |
| `ltv_transaction_base` | Tekilleştirilmiş satın alma veya iade olayı | Temiz temel veri |
| `ltv_data_quality` | Tek satır | Analize giren verinin kapsamı |
| `ltv_customer_summary` | Bir `user_id` | Müşteri LTV özeti |
| `ltv_overall_summary` | Tek satır | Genel istatistikler |
| `ltv_decile_summary` | LTV dilimi | Müşteri ve gelir dağılımı |
| `ltv_percentile_distribution` | Yüzdelik dilim | Gelir yoğunlaşma eğrisi |
| `ltv_monthly_metrics` | Bir takvim ayı | E-ticaret ve dijital davranış metrikleri |
| `ltv_monthly_metric_changes` | Ay × metrik | MoM ve YoY değerleri |
| `ltv_cohort_summary` | İlk satın alma ayı | Temel kohort büyüklüğü, LTV ve tekrar oranı |

## Aylık metrik tanımları

| Metrik | Bu paketteki hesap |
| --- | --- |
| E-ticaret ARPU | Net satın alma geliri / aktif kullanıcı |
| E-ticaret ARPPU | Net satın alma geliri / satın alan kullanıcı |
| AOV | Brüt satın alma geliri / sipariş |
| Net AOV | Net satın alma geliri / sipariş |
| Oturum başına gelir | Net satın alma geliri / oturum |
| Satın alma sıklığı | Sipariş / satın alan kullanıcı |
| Satın alan kullanıcı oranı | Satın alan kullanıcı / aktif kullanıcı |
| Oturum satın alma oranı | Satın alma gerçekleşen oturum / tüm oturumlar |
| Aylık tekrar satın alan oranı | Ay içinde en az iki sipariş veren kullanıcı / o ay satın alan kullanıcı |
| İade tutarı payı | İade tutarı / brüt satın alma geliri |

`MoM`, eksiksiz bir ayın bir önceki takvim ayıyla; `YoY`, geçen yılın aynı ayıyla karşılaştırılmasıdır. Karşılaştırma dönemi yoksa veya eksikse sonuç boş bırakılır; sıradaki mevcut aya atlanmaz. Oran metriklerinde mutlak değişim yüzde puan olarak gösterilir. Kısmi aylar aylık tabloda saklanır, ancak kartlar ve karşılaştırmalar en güncel eksiksiz ayı seçer.

## Kurulum

GitHub deposu oluşturulduktan sonra Colab'da:

```python
%pip install -q --upgrade "ga4-ltv-toolkit @ git+https://github.com/yasinsariyildizz/ga4_ltv_analyzer.git@main"
```

Ardından Google hesabı doğrulanır:

```python
from google.colab import auth
auth.authenticate_user()
```

Hazır notebook: [`notebooks/GA4_LTV_Analysis_Colab.ipynb`](notebooks/GA4_LTV_Analysis_Colab.ipynb)

GitHub kurulumu yapılmadan denemek için depodaki `ga4_ltv.py` dosyası doğrudan Colab'a yüklenebilir. Bu dosya SQL şablonlarını da içinde taşır; ek dosyaya ihtiyaç duymaz.

## LTV'nin anlamı

Bu paket **gözlemlenmiş LTV** hesaplar:

```text
Müşteri LTV = satın alma gelirleri − iade tutarları
```

Örneğin bir müşteri 900 TL ve 600 TL tutarında iki sipariş verip 200 TL iade yaptıysa gözlemlenmiş LTV'si 1.300 TL'dir.

Bu değer müşterinin gelecekte getireceği geliri tahmin etmez. Bu modüldeki kohort bölümü özellikle temel seviyede tutulur: müşterileri ilk satın alma ayına göre gruplar ve her grubun bugüne kadar gözlenen LTV'sini özetler. Aynı müşteri yaşında ayrıntılı kohort eğrileri ayrı kohort analizinin konusu olacaktır.

Müşteri LTV'si yalnızca `user_id` ile hesaplanır. Aylık dijital metriklerde ise kapsamı korumak için varsa `user_id`, yoksa `user_pseudo_id` kullanılır. Bu nedenle aylık satın alan kullanıcı sayısı ile LTV müşteri sayısı birebir aynı olmayabilir.

## Para birimi seçimi

Paket yeni bir giriş alanı istemez:

- Satın almalar tek para birimindeyse yerel gelir alanını kullanır.
- Birden fazla para birimi varsa karşılaştırılabilir olması için USD alanına geçer.
- Hem yerel hem USD tutarlar BigQuery sonuçlarında tutulur.

## Bilinmesi gereken sınırlar

- `user_id` boş olan satın almalar müşteri LTV hesabına girmez; veri kalitesi tablosunda ayrıca sayılır.
- Analiz yalnızca seçilen GA4 tablolarında görülen dönemi kapsar.
- GA4'te eksik veya hatalı iletilen satın alma, iade ve para birimi bilgileri sonucu etkiler.
- Bu çalışma kâr değil gelir LTV'sidir; ürün maliyeti ve pazarlama maliyeti dahil değildir.
- ROAS, CPA, CAC, CPC ve reklam maliyeti verisi isteyen diğer metrikler bu dört GA4 girdisinden güvenilir biçimde hesaplanamaz; ayrıca reklam maliyeti tablosu gerekir.
- Temel kohortların gözlem süreleri farklıdır. Eski kohortların daha yüksek LTV göstermesi tek başına daha kaliteli oldukları anlamına gelmez.
- GA4 arayüzündeki Google Signals ve davranış modelleme BigQuery dışa aktarımında bulunmadığı için kullanıcı metrikleri arayüzle birebir eşleşmeyebilir.
- `user_id` alanında e-posta veya telefon gibi doğrudan kişisel bilgi tutulmamalıdır.

Ayrıntılı yöntem ve yorumlama: [`docs/ANALYSIS_GUIDE_TR.md`](docs/ANALYSIS_GUIDE_TR.md)

Resmî kaynaklar: [GA4 BigQuery dışa aktarma şeması](https://support.google.com/analytics/answer/7029846?hl=tr) · [GA4 metrik tanımları](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema?hl=tr)
