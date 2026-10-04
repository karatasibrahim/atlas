import { markup } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { AtlasBarkodApp } from "@atlas_barkod/barkod_app/barkod_app";

const KALITE = { ad: "Kalite Kontrol", ikon: "verified", renk: "danger" };

/**
 * Atlas Barkod uygulamasına kalite kontrol ekranı: bekleyen kontroller, belgedeki kontroller,
 * ATL:QC QR kodu ile kontrol açma; geçti/kaldı, ölçüm, kontrol listesi, numune ve fotoğraf.
 */
patch(AtlasBarkodApp.prototype, {
    setup() {
        super.setup();
        this.islemler = { ...this.islemler, kalite: KALITE };
        Object.assign(this.state, { kontrol: null, kontrolGiris: {}, kontrolDonus: null });
    },

    get islemAnahtarlari() {
        return Object.keys(this.islemler);
    },

    get islemAdi() {
        return this.state.islem ? this.islemler[this.state.islem].ad : "";
    },

    kontrolHazirla(kontrol) {
        kontrol.talimat = kontrol.talimat ? markup(kontrol.talimat) : "";
        kontrol.basarisiz_mesaj = kontrol.basarisiz_mesaj ? markup(kontrol.basarisiz_mesaj) : "";
        this.state.kontrol = kontrol;
        const maddeler = {};
        for (const m of kontrol.maddeler) {
            maddeler[m.id] = m.sonuc;
        }
        this.state.kontrolGiris = {
            olcum: kontrol.olcum ?? "",
            test_edilen: kontrol.test_edilen,
            hatali: kontrol.hatali,
            notlar: kontrol.notlar,
            maddeler,
            foto: null,
        };
    },

    async kaliteAc(id) {
        // Belge ekranından gelindiyse geri dönüşte o belge açılır
        if (this.state.ekran === "belge" && this.state.islem !== "kalite") {
            this.state.kontrolDonus = { id: this.state.belge.id, islem: this.state.islem };
        } else if (this.state.ekran !== "kalite") {
            this.state.kontrolDonus = null;
        }
        const kontrol = await this.cagir("kalite_ac", [id]);
        this.kontrolHazirla(kontrol);
        Object.assign(this.state, { ekran: "kalite", onay: null });
    },

    async belgeAc(id, islem = this.state.islem) {
        if (islem === "kalite") {
            this.state.islem = "kalite";
            return this.kaliteAc(id);
        }
        return super.belgeAc(id, islem);
    },

    async geri() {
        if (this.state.ekran === "kalite") {
            // Kontrol, ekran değişene kadar başlıkta kullanılıyor; temizlenmiyor
            const donus = this.state.kontrolDonus;
            this.state.kontrolDonus = null;
            if (donus) {
                return super.belgeAc(donus.id, donus.islem);
            }
            Object.assign(this.state, { ekran: "liste", islem: "kalite" });
            return this.listeYukle();
        }
        return super.geri();
    },

    async kodIsle(kod) {
        if (this.state.ekran === "belge") {
            return super.kodIsle(kod);
        }
        try {
            const bilgi = await this.cagir("cozumle", [kod]);
            if (bilgi.kalite) {
                this.state.kontrolDonus = null;
                this.state.ekran = "liste";
                await this.kaliteAc(bilgi.kalite.id);
                this.geriBildirim("ok");
            } else if (bilgi.belge && bilgi.belge.islem) {
                await super.belgeAc(bilgi.belge.id, bilgi.belge.islem);
            } else if (bilgi.lokasyon && this.state.islem === "sayim") {
                await super.belgeAc(bilgi.lokasyon.id, "sayim");
            } else {
                Object.assign(this.state, { bilgi, ekran: "bilgi" });
                this.geriBildirim("ok");
            }
        } catch {
            // mesaj `cagir` içinde gösterildi
        } finally {
            this.odakla();
        }
    },

    kontrolDeger(alan, ev) {
        this.state.kontrolGiris[alan] = ev.target.value;
    },

    maddeSec(maddeId, sonuc) {
        this.state.kontrolGiris.maddeler[maddeId] = sonuc;
    },

    fotoSecildi(ev) {
        const dosya = ev.target.files && ev.target.files[0];
        if (!dosya) {
            return;
        }
        const okuyucu = new FileReader();
        okuyucu.onload = () => {
            this.state.kontrolGiris.foto = String(okuyucu.result).split(",")[1];
        };
        okuyucu.readAsDataURL(dosya);
    },

    async kontrolSonuc(islem) {
        const giris = this.state.kontrolGiris;
        try {
            const sonuc = await this.cagir("kalite_sonuc", [this.state.kontrol.id, islem, {
                olcum: giris.olcum,
                test_edilen: giris.test_edilen,
                hatali: giris.hatali,
                notlar: giris.notlar,
                maddeler: giris.maddeler,
                foto: giris.foto,
            }]);
            this.kontrolHazirla(sonuc.kontrol);
            this.bildir(sonuc.mesaj, sonuc.sonuc);
        } catch {
            // gösterildi
        }
    },

    kontrolYazdir() {
        window.open(`/report/pdf/atlas_kalite.report_kalite_kontrol/${this.state.kontrol.id}`, "_blank");
    },

    durumAdi(durum) {
        return { bekliyor: "Bekliyor", gecti: "Geçti", kaldi: "Kaldı" }[durum] || durum;
    },

    durumRenk(durum) {
        return { bekliyor: "warning", gecti: "success", kaldi: "danger" }[durum] || "secondary";
    },
});
