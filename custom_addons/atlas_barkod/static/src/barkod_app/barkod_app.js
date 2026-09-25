import { Component, onMounted, onWillStart, proxy, signal, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { scanBarcode } from "@web/core/barcode/barcode_dialog";
import { isBarcodeScannerSupported } from "@web/core/barcode/barcode_video_scanner";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const ISLEMLER = {
    mal_kabul: { ad: "Mal Kabul", ikon: "download", renk: "primary" },
    sevkiyat: { ad: "Sevkiyat Toplama", ikon: "local_shipping", renk: "success" },
    uretim: { ad: "Üretim", ikon: "factory", renk: "warning" },
    sayim: { ad: "Stok Sayımı", ikon: "checklist", renk: "info" },
};

/**
 * Atlas Barkod: telefon kamerası veya klavye olarak çalışan okuyucu ile mal kabul, sevkiyat,
 * stok sayımı ve üretimde okutma. Tüm iş mantığı sunucudaki `atlas.barkod` modelindedir.
 */
export class AtlasBarkodApp extends Component {
    static template = "atlas_barkod.App";
    props = useProps(standardActionServiceProps);
    kodInputRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.islemler = ISLEMLER;
        this.kameraVar = isBarcodeScannerSupported();
        this.state = proxy({
            ekran: "ana",
            islem: null,
            ozet: {},
            liste: [],
            arama: "",
            belge: null,
            bilgi: null,
            miktar: 1,
            mesaj: null,
            mesajTip: "ok",
            onay: null,
            sifirla: false,
            seriIds: [],
            yukleniyor: false,
        });
        onWillStart(() => this.ozetYukle());
        onMounted(() => this.odakla());
    }

    // ------------------------------------------------------------------
    // Yardımcılar
    // ------------------------------------------------------------------

    async cagir(method, args) {
        this.state.yukleniyor = true;
        try {
            return await this.orm.call("atlas.barkod", method, args);
        } catch (error) {
            this.bildir(error.data?.message || error.message || String(error), "hata");
            throw error;
        } finally {
            this.state.yukleniyor = false;
        }
    }

    bildir(mesaj, tip = "ok") {
        this.state.mesaj = mesaj;
        this.state.mesajTip = tip;
        this.geriBildirim(tip);
    }

    geriBildirim(tip) {
        try {
            if (navigator.vibrate && navigator.userActivation?.hasBeenActive) {
                navigator.vibrate(tip === "hata" ? [120, 60, 120] : 40);
            }
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.frequency.value = tip === "hata" ? 220 : tip === "uyari" ? 520 : 880;
            gain.gain.value = 0.08;
            osc.connect(gain).connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + (tip === "hata" ? 0.35 : 0.12));
        } catch {
            // ses/titreşim desteklenmiyorsa sessiz geç
        }
    }

    odakla() {
        // El okuyucular (klavye gibi çalışan) odaktaki kutuya yazar; mobilde klavye açılmasın diye yalnızca masaüstünde
        const input = this.kodInputRef();
        if (input && !("ontouchstart" in window)) {
            input.focus();
        }
    }

    get islemAnahtarlari() {
        return Object.keys(ISLEMLER);
    }

    mesajKapat() {
        this.state.mesaj = null;
    }

    onayIptal() {
        this.state.onay = null;
    }

    get islemAdi() {
        return this.state.islem ? ISLEMLER[this.state.islem].ad : "";
    }

    get ilerleme() {
        const satirlar = this.state.belge?.satirlar || [];
        if (this.state.islem === "sayim") {
            return { tamam: satirlar.filter((s) => s.sayilan !== null).length, toplam: satirlar.length };
        }
        return { tamam: satirlar.filter((s) => s.tamam).length, toplam: satirlar.length };
    }

    // ------------------------------------------------------------------
    // Gezinme
    // ------------------------------------------------------------------

    async ozetYukle() {
        this.state.ozet = await this.cagir("ana_ekran", []);
    }

    async anaEkran() {
        Object.assign(this.state, { ekran: "ana", islem: null, belge: null, bilgi: null, onay: null, seriIds: [] });
        await this.ozetYukle();
    }

    async islemSec(islem) {
        Object.assign(this.state, { ekran: "liste", islem, arama: "", belge: null, mesaj: null, seriIds: [] });
        await this.listeYukle();
    }

    async listeYukle() {
        this.state.liste = await this.cagir("belge_listesi", [this.state.islem, this.state.arama]);
    }

    async aramaDegisti(ev) {
        this.state.arama = ev.target.value;
        await this.listeYukle();
    }

    async belgeAc(id, islem = this.state.islem) {
        this.state.islem = islem;
        this.state.belge = await this.cagir("belge_ac", [islem, id]);
        Object.assign(this.state, { ekran: "belge", onay: null, seriIds: [], miktar: 1 });
        this.odakla();
    }

    async geri() {
        if (this.state.ekran === "belge") {
            this.state.ekran = "liste";
            this.state.belge = null;
            this.state.onay = null;
            await this.listeYukle();
        } else if (this.state.ekran === "bilgi" && this.state.islem) {
            this.state.ekran = "liste";
        } else {
            await this.anaEkran();
        }
    }

    cikis() {
        window.location.href = "/odoo";
    }

    // ------------------------------------------------------------------
    // Okutma
    // ------------------------------------------------------------------

    async kameraAc() {
        try {
            const kod = await scanBarcode(this.env);
            if (kod) {
                await this.kodIsle(kod);
            }
        } catch (error) {
            this.bildir(error?.message || "Kamera açılamadı; tarayıcı izinlerini kontrol edin.", "hata");
        }
    }

    async inputTus(ev) {
        if (ev.key === "Enter") {
            const kod = ev.target.value.trim();
            ev.target.value = "";
            if (kod) {
                await this.kodIsle(kod);
            }
        }
    }

    miktarDegisti(ev) {
        const deger = parseFloat(String(ev.target.value).replace(",", "."));
        this.state.miktar = deger > 0 ? deger : 1;
    }

    async kodIsle(kod) {
        try {
            if (this.state.ekran === "belge") {
                const sonuc = await this.cagir("okut", [this.state.islem, this.state.belge.id, kod, this.state.miktar]);
                this.state.belge = sonuc.belge;
                this.state.miktar = 1;
                this.bildir(sonuc.mesaj, sonuc.sonuc);
            } else {
                // Liste / ana ekranda okutulan kod: belgeyse aç, değilse bilgi göster
                const bilgi = await this.cagir("cozumle", [kod]);
                if (bilgi.belge && bilgi.belge.islem) {
                    await this.belgeAc(bilgi.belge.id, bilgi.belge.islem);
                } else if (bilgi.lokasyon && this.state.islem === "sayim") {
                    await this.belgeAc(bilgi.lokasyon.id, "sayim");
                } else {
                    Object.assign(this.state, { bilgi, ekran: "bilgi" });
                    this.geriBildirim("ok");
                }
            }
        } catch {
            // mesaj `cagir` içinde gösterildi
        } finally {
            this.odakla();
        }
    }

    // ------------------------------------------------------------------
    // Belge işlemleri
    // ------------------------------------------------------------------

    async seriUret(satir) {
        try {
            const sonuc = await this.cagir("seri_uret", [this.state.islem, this.state.belge.id, satir ? satir.move_id : false]);
            this.state.belge = sonuc.belge;
            this.state.seriIds = sonuc.seri_ids;
            this.bildir(sonuc.mesaj, "ok");
        } catch {
            // gösterildi
        }
    }

    async etiketYazdir(seriIds = this.state.seriIds) {
        try {
            const url = await this.cagir("etiket_url", [seriIds]);
            window.open(url, "_blank");
        } catch {
            // gösterildi
        }
    }

    uretimQrYazdir() {
        window.open(`/report/pdf/mrp.report_mrporder/${this.state.belge.id}`, "_blank");
    }

    dogrulaSor() {
        this.state.onay = this.state.islem;
    }

    async dogrula(kalanIcinBelge = true) {
        try {
            const sonuc = await this.cagir("dogrula", [
                this.state.islem, this.state.belge.id, kalanIcinBelge, this.state.sifirla,
            ]);
            this.state.onay = null;
            this.bildir(sonuc.mesaj, "ok");
            if (sonuc.seri_ids?.length) {
                this.state.seriIds = sonuc.seri_ids;
            }
            if (this.state.islem === "sayim") {
                this.state.belge = await this.cagir("sayim_ac", [this.state.belge.id]);
            } else if (sonuc.kalan_belge_id) {
                await this.belgeAc(sonuc.kalan_belge_id);
                this.bildir(sonuc.mesaj, "ok");
            } else {
                this.state.ekran = "liste";
                this.state.belge = null;
                await this.listeYukle();
            }
        } catch {
            // gösterildi
        }
    }

    sifirlaDegisti(ev) {
        this.state.sifirla = ev.target.checked;
    }
}

registry.category("actions").add("atlas_barkod.app", AtlasBarkodApp);
