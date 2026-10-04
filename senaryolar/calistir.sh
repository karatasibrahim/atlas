#!/bin/bash
# Atlas senaryo testleri: her test Odoo shell'de çalışır, sonunda tüm değişiklikleri geri alır (veritabanı değişmez).
# Kullanım: senaryolar/calistir.sh [test_adi ...]   (proje kökünden)
cd "$(dirname "$0")/.." || exit 1
testler=("$@")
[ ${#testler[@]} -eq 0 ] && testler=(test_cari test_fis test_kasa_banka test_cek test_rapor test_donem test_stok test_barkod test_tr test_kalite test_plm test_mps)
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
