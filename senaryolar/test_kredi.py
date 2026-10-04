from datetime import date
from odoo import fields
ok = lambda cond, msg: print(("  OK  " if cond else "  HATA"), msg)
c = env.company; K = env['atlas.kredi']; J = env['account.journal']
def iban(bank, acc):
    bban = f"{bank}0{acc:016d}"; check = 98 - int(bban + '292700') % 97; return f"TR{check:02d}{bban}"
banka = J.create({'name': 'KRD Garanti', 'code': 'KGR', 'type': 'bank', 'bank_account_number': iban('00062', 555111)})
ok(c.atlas_kredi_taksit_hesap_id.code == '303000' and c.atlas_kredi_uzun_hesap_id.account_type == 'liability_non_current', "kredi hesapları; 400 uzun vadeli borç tipine düzeltildi")
k = K.create({'aciklama': 'İşletme kredisi', 'banka_journal_id': banka.id, 'kullanim_tarihi': date(2026, 1, 15), 'tutar': 120000,
              'masraf': 1000, 'faiz_orani': 3, 'faiz_donemi': 'aylik', 'bsmv_orani': 5, 'taksit_sayisi': 24, 'odeme_tipi': 'esit_taksit'})
k.action_plan_olustur()
t = k.taksit_ids.sorted('no')
rg = 0.03 * 1.05; beklenen = round(120000 * rg / (1 - (1 + rg) ** -24), 2)
ok(k.name.startswith('KRD') and len(t) == 24 and t[0].vade == date(2026, 2, 15) and t[0].faiz == 3600 and t[0].bsmv == 180, f"plan: 24 taksit, ilk faiz 3.600 + BSMV 180 ({k.name})")
ok(abs(t[0].toplam - beklenen) < 0.02 and abs(t[10].toplam - beklenen) < 0.02 and round(sum(t.mapped('anapara')), 2) == 120000, f"eşit taksit {beklenen:,.2f}, anapara toplamı 120.000")
ok(t[-1].kalan_anapara == 0 and abs(t[-1].toplam - beklenen) < 1, "son taksitte kalan anapara sıfır")
k.action_kullan()
fis = k.move_ids
kul = fis.filtered(lambda m: m.atlas_kredi_rol == 'kullanim'); vir = fis.filtered(lambda m: m.atlas_kredi_rol == 'virman')
tak = fis.filtered(lambda m: m.atlas_kredi_rol == 'taksit')
bak = lambda moves, kod: round(sum(moves.line_ids.filtered(lambda l: l.parent_state == 'posted' and l.account_id.code == kod).mapped('balance')), 2)
uzun = round(sum(x.anapara for x in t if x.vade.year == 2028), 2)
ok(kul.state == 'posted' and bak(kul, '103001') == 119000 and bak(kul, '780000') == 1000 and bak(kul, '303000') == -(120000 - uzun) and bak(kul, '400000') == -uzun,
   f"kullanım: banka(transit) 119.000, masraf 1.000, 303 {120000-uzun:,.2f}, 400 {uzun:,.2f}")
ok(len(vir) == 1 and vir.date == date(2027, 12, 31) and vir.state == 'draft' and vir.auto_post == 'at_date', "400→303 virmanı 31.12.2027 (otomatik)")
gecmis = tak.filtered(lambda m: m.date <= date(2026, 10, 4))
ok(len(tak) == 24 and all(m.state == 'posted' for m in gecmis) and len(gecmis) == 8 and all(m.state == 'draft' for m in tak - gecmis), "vadesi geçen 8 taksit onaylı, kalanlar taslak/otomatik")
t1 = t[0].move_id
ok(bak(t1, '303000') == t[0].anapara and bak(t1, '780000') == 3780 and bak(t1, '103001') == -t[0].toplam, "taksit fişi: anapara 303, faiz+BSMV 780, banka")
k.invalidate_recordset()
ok(len(k.taksit_ids.filtered(lambda x: x.durum == 'odendi')) == 8 and k.sonraki_taksit_id.no == 9, f"8 taksit ödendi, sonraki {k.sonraki_taksit_id.vade}")
st = env['account.bank.statement.line'].create({'journal_id': banka.id, 'date': date(2026, 1, 15), 'amount': 119000, 'payment_ref': 'KREDI KULLANDIRIM'})
ok(st._atlas_find_pending_line().move_id == kul, "banka ekstresinde kullanım satırı bekleyen kayıt olarak bulundu")
k.write({'kapama_tarihi': date(2026, 10, 4), 'kapama_faiz': 500})
k.action_erken_kapat()
k.invalidate_recordset()
posted = k.move_ids.filtered(lambda m: m.state == 'posted')
ok(k.durum == 'kapandi' and not k.move_ids.filtered(lambda m: m.state == 'draft') and bak(posted, '303000') + bak(posted, '400000') == 0,
   "erken kapama: gelecek fişler silindi, 303+400 bakiyesi sıfır")
ok(all(x.durum == 'odendi' for x in k.taksit_ids) and k.kalan_anapara == 0, "tüm taksitler kapandı")
k2 = K.create({'banka_journal_id': banka.id, 'kullanim_tarihi': date(2026, 9, 1), 'tutar': 12000, 'faiz_orani': 36, 'faiz_donemi': 'yillik',
               'bsmv_orani': 0, 'taksit_sayisi': 6, 'odeme_tipi': 'esit_anapara'})
k2.action_plan_olustur(); t2 = k2.taksit_ids.sorted('no')
ok(all(x.anapara == 2000 for x in t2) and t2[0].faiz == 360 and t2[1].faiz == 300, "eşit anaparalı: 2.000 anapara, faiz azalan (yıllık %36 → aylık %3)")
k3 = K.create({'banka_journal_id': banka.id, 'kullanim_tarihi': date(2026, 9, 1), 'tutar': 50000, 'faiz_orani': 2, 'bsmv_orani': 0, 'taksit_sayisi': 3, 'odeme_tipi': 'balon'})
k3.action_plan_olustur(); t3 = k3.taksit_ids.sorted('no')
ok([x.anapara for x in t3] == [0, 0, 50000] and all(x.faiz == 1000 for x in t3), "balon: anapara vade sonunda, her ay 1.000 faiz")
k2.action_kullan()
ok(k2.move_ids.filtered(lambda m: m.atlas_kredi_rol == 'kullanim').line_ids.filtered(lambda l: l.balance < 0).account_id.code == '300000', "1 yıldan kısa kredi 300'e")
k2.action_iptal()
ok(k2.durum == 'taslak' and not k2.move_ids, "geri alma: fişler ters kayıt / silme ile kaldırıldı")
env.cr.rollback(); print("(geri alındı)")
