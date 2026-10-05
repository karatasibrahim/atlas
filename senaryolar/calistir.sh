#!/bin/bash
# Atlas senaryo testleri: her test Odoo shell'de çalışır, sonunda tüm değişiklikleri geri alır (veritabanı değişmez).
# Kullanım: senaryolar/calistir.sh [test_adi ...]   (proje kökünden)
cd "$(dirname "$0")/.." || exit 1
testler=("$@")
[ ${#testler[@]} -eq 0 ] && testler=(test_cari test_fis test_kasa_banka test_cek test_rapor test_donem test_stok test_barkod test_tr test_kalite test_plm test_mps test_planlama test_irsaliye test_tahakkuk test_hatirlatma test_butce test_kredi test_ebelge test_beyanname test_shopfloor test_oee test_odeme_talimati test_abonelik test_kiralama test_destek test_belgeler test_imza test_onay test_studio test_mobil test_gorunum test_zaman test_saha test_pazarlama test_whatsapp test_voip test_iot test_mysoft test_bordro test_degerlendirme test_mevzuat test_finansal test_belgeler_kopru test_ekstre_bicim test_ai test_veri test_tahakkuk_inceleme)
toplam_ok=0; toplam_hata=0
for t in "${testler[@]}"; do
    out=$(.venv/bin/python odoo/odoo-bin shell -c odoo.conf -d "${ATLAS_DB:-atlas}" --no-http < "senaryolar/$t.py" 2>&1)
    ok=$(grep -c '^  OK' <<< "$out"); hata=$(grep -c '^  HATA' <<< "$out"); tb=$(grep -c '^Traceback' <<< "$out")
    printf "%-18s OK=%-3s HATA=%-2s Traceback=%s\n" "$t" "$ok" "$hata" "$tb"
    grep -E '^  HATA' <<< "$out"
    [ "$tb" -gt 0 ] && grep -v ' INFO ' <<< "$out" | tail -8
    toplam_ok=$((toplam_ok + ok)); toplam_hata=$((toplam_hata + hata + tb))
done
echo "Toplam: $toplam_ok başarılı, $toplam_hata hata"
[ "$toplam_hata" -eq 0 ]
