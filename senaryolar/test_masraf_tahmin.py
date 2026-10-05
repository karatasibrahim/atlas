ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
E_ = env['hr.expense']
P = env['product.product']
yemek = P.create({'name': 'MT Yemek', 'can_be_expensed': True})
ulasim = P.create({'name': 'MT Ulaşım', 'can_be_expensed': True})
calisan = env['hr.employee'].create({'name': 'MT Çalışan'})
for ad, urun in [('Öğle yemeği müşteri ziyareti', yemek), ('Akşam yemeği proje ekibi', yemek), ('Taksi havalimanı', ulasim),
                 ('Taksi Kadıköy ofis', ulasim), ('Otopark ücreti AVM', ulasim)]:
    E_.create({'name': ad, 'employee_id': calisan.id, 'product_id': urun.id})
ok(E_._atlas_kategori_tahmin('Taksi otel transferi') == ulasim and E_._atlas_kategori_tahmin('YEMEK - müşteri') == yemek,
   "açıklamadan kategori tahmini (Türkçe harf/aksan duyarsız)")
ok(not E_._atlas_kategori_tahmin('Kırtasiye alımı'), "benzer geçmiş yoksa tahmin yapılmaz")
yeni = E_.create({'name': 'Taksi müşteri ziyareti', 'employee_id': calisan.id})
ok(yeni.product_id == ulasim, "yeni masrafta kategori otomatik dolduruldu")
elle = E_.create({'name': 'Taksi', 'employee_id': calisan.id, 'product_id': yemek.id})
ok(elle.product_id == yemek, "kullanıcının seçtiği kategori değiştirilmez")
env.cr.rollback(); print("(geri alındı)")
