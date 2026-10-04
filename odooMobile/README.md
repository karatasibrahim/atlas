# Atlas Mobil

Atlas ERP (Odoo 20) için Flutter mobil uygulaması (Android / iOS). Sunucu tarafı API'si `custom_addons/atlas_mobil` modülündedir;
depo işlemleri `atlas_barkod` metotlarını kullanır.

## Özellikler

- **Ana sayfa:** satış, açık alacak, onay ve fırsat göstergeleri, 7 günlük satış grafiği, depo iş listesi, aktiviteler, konumlu mesai giriş/çıkış
- **Satış:** teklif/sipariş listesi, detay, barkodla ürün ekleyerek teklif oluşturma, siparişe çevirme
- **CRM:** aşama sekmeli fırsat hattı, aşama değiştirme, kazanıldı/kaybedildi, not
- **Cariler:** arama, bakiye, açık faturalar, arama/e-posta/yol tarifi, yeni cari
- **Depo:** mal kabul, sevkiyat, üretim, stok sayımı (kamerayla sürekli okutma), seri üretme
- **Onay merkezi:** Atlas onay talepleri + masraf + izin onayları tek listede; yeni onay talebi
- **Personel:** fiş fotoğraflı masraf, izin talebi, giriş/çıkış geçmişi
- **Genel okutma:** ürün / seri / lokasyon / belge QR'ını tanıyıp ilgili ekrana yönlendirir
- Açık/koyu tema, 4 renk teması (Odoo Patlıcan, Odoo Community, Odoo Turkuaz, Atlas Lacivert), biyometrik kilit

## Çalıştırma

```bash
cd odooMobile
flutter pub get
flutter run            # bağlı cihaz / emülatör
```

Sunucuda `atlas_mobil` modülü kurulu olmalıdır. Android emülatöründen bilgisayardaki Odoo'ya `http://10.0.2.2:8069`,
iOS simülatöründen `http://127.0.0.1:8069` adresiyle bağlanılır.

> Geliştirme kolaylığı için Android'de `usesCleartextTraffic`, iOS'ta `NSAllowsArbitraryLoads` açıktır (yerel ağdaki http sunucular).
> Canlıya çıkmadan önce sunucuyu https'e alıp bu ayarları kapatın.

## Yapı

```
lib/core/       api (JSON-RPC, oturum), session (durum/tercihler), theme, format (TR biçimleri)
lib/widgets/    ortak bileşenler, marka
lib/features/   ekranlar (dashboard, sales, crm, partners, products, inventory, scan, approvals, hr, activities, profile)
```
