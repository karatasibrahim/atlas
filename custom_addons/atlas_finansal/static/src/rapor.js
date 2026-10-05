import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const { DateTime } = luxon;

const sayiBicim = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const oranBicim = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 4 });

/** Tarih ön ayarları → [başlangıç, bitiş] */
export function donemAraligi(kod, bugun = DateTime.local()) {
    const b = bugun.startOf("day");
    switch (kod) {
        case "bu_ay":
            return [b.startOf("month"), b.endOf("month")];
        case "gecen_ay":
            return [b.minus({ months: 1 }).startOf("month"), b.minus({ months: 1 }).endOf("month")];
        case "bu_ceyrek":
            return [b.startOf("quarter"), b.endOf("quarter")];
        case "gecen_ceyrek":
            return [b.minus({ quarters: 1 }).startOf("quarter"), b.minus({ quarters: 1 }).endOf("quarter")];
        case "gecen_yil":
            return [b.minus({ years: 1 }).startOf("year"), b.minus({ years: 1 }).endOf("year")];
        case "bugun":
            return [b, b];
        default:
            return [b.startOf("year"), b.endOf("year")];
    }
}

export class AtlasFinansalRapor extends Component {
    static template = "atlas_finansal.Rapor";
    static components = { MultiRecordSelector };
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.raporId = this.props.action.params?.rapor_id || this.props.action.context?.rapor_id;
        const onceki = this.props.state?.secenekler;
        this.state = proxy({
            veri: null,
            secenekler: onceki || this.ilkSecenekler(),
            yukleniyor: false,
            notAnahtar: null,
            notMetin: "",
            yevmiyeAcik: false,
        });
        useSetupAction({ getLocalState: () => ({ secenekler: this.state.secenekler }) });
        onWillStart(() => this.yukle());
    }

    ilkSecenekler() {
        // Tarihleri sunucu belirler: aralık raporlarında bu yılın tamamı, tek tarihli raporlarda bugün
        return { donem_kodu: "bu_yil", sifir_gizle: true, karsilastirma: { tur: "yok", adet: 1 } };
    }

    async yukle() {
        this.state.yukleniyor = true;
        try {
            const veri = await this.orm.call("atlas.finansal.rapor", "rapor_verisi", [[this.raporId], this.state.secenekler]);
            const donemKodu = this.state.secenekler.donem_kodu;
            this.state.secenekler = { ...veri.secenekler, donem_kodu: donemKodu };
            this.state.veri = veri;
        } catch (hata) {
            this.hataGoster(hata);
        } finally {
            this.state.yukleniyor = false;
        }
    }

    hataGoster(hata) {
        this.notification.add(hata.data?.message || hata.message || String(hata), { type: "danger" });
    }

    // ------------------------------------------------------------------ seçenekler
    guncelle(degisiklik, yenidenYukle = true) {
        this.state.secenekler = { ...this.state.secenekler, ...degisiklik };
        if (yenidenYukle) {
            return this.yukle();
        }
    }

    get tekTarih() {
        return this.state.veri?.rapor.tarih_modu === "tek";
    }

    donemSec(ev) {
        const kod = ev.target.value;
        if (kod === "ozel") {
            this.state.secenekler = { ...this.state.secenekler, donem_kodu: "ozel" };
            return;
        }
        const [bas, bit] = donemAraligi(kod);
        const bugun = DateTime.local().toISODate();
        let bitis = bit.toISODate();
        if (this.tekTarih && kod.startsWith("bu_") && bitis > bugun) {
            bitis = bugun;
        }
        this.guncelle({ donem_kodu: kod, tarih_bas: bas.toISODate(), tarih_bit: bitis });
    }

    tarihDegisti(alan, ev) {
        if (ev.target.value) {
            this.guncelle({ [alan]: ev.target.value, donem_kodu: "ozel" });
        }
    }

    karsilastirmaSec(ev) {
        this.guncelle({ karsilastirma: { ...this.state.secenekler.karsilastirma, tur: ev.target.value } });
    }

    karsilastirmaAdet(ev) {
        const adet = Math.max(1, Math.min(12, parseInt(ev.target.value || "1", 10) || 1));
        this.guncelle({ karsilastirma: { ...this.state.secenekler.karsilastirma, adet } });
    }

    secenekDegistir(alan) {
        this.guncelle({ [alan]: !this.state.secenekler[alan] });
    }

    metinSecenek(alan, ev) {
        this.guncelle({ [alan]: ev.target.value });
    }

    yevmiyeSec(id) {
        const secili = new Set(this.state.secenekler.yevmiye_ids || []);
        if (secili.has(id)) {
            secili.delete(id);
        } else {
            secili.add(id);
        }
        this.guncelle({ yevmiye_ids: [...secili] });
    }

    get yevmiyeEtiketi() {
        const secili = this.state.secenekler.yevmiye_ids || [];
        if (!secili.length) {
            return _t("Tüm yevmiyeler");
        }
        return secili.length === 1
            ? this.state.veri.yevmiyeler.find((y) => y.id === secili[0])?.ad || "1"
            : _t("%s yevmiye", secili.length);
    }

    // ------------------------------------------------------------------ satırlar
    gorunurSatirlar() {
        return this.state.veri ? this.state.veri.satirlar : [];
    }

    async satirTikla(satir) {
        if (satir.sinif === "daha") {
            return this.dahaYukle(satir);
        }
        if (!satir.acilabilir) {
            return;
        }
        const satirlar = this.state.veri.satirlar;
        const acik = new Set(this.state.secenekler.acik || []);
        const kapali = new Set(this.state.secenekler.kapali || []);
        if (satir.acik) {
            const onEk = satir.anahtar + "|";
            this.state.veri.satirlar = satirlar.filter((s) => !s.anahtar.startsWith(onEk));
            satir.acik = false;
            acik.delete(satir.anahtar);
            kapali.add(satir.anahtar);
            this.state.secenekler = { ...this.state.secenekler, acik: [...acik], kapali: [...kapali] };
            return;
        }
        acik.add(satir.anahtar);
        kapali.delete(satir.anahtar);
        this.state.secenekler = { ...this.state.secenekler, acik: [...acik], kapali: [...kapali] };
        try {
            const alt = await this.orm.call("atlas.finansal.rapor", "alt_satirlar", [[this.raporId], this.state.secenekler, satir.anahtar]);
            const i = this.state.veri.satirlar.findIndex((s) => s.anahtar === satir.anahtar);
            const yeni = [...this.state.veri.satirlar];
            yeni[i] = { ...yeni[i], acik: true };
            yeni.splice(i + 1, 0, ...alt);
            this.state.veri.satirlar = yeni;
        } catch (hata) {
            this.hataGoster(hata);
        }
    }

    async dahaYukle(satir) {
        try {
            const alt = await this.orm.call("atlas.finansal.rapor", "alt_satirlar", [[this.raporId], this.state.secenekler, satir.anahtar]);
            const yeni = [...this.state.veri.satirlar];
            const i = yeni.findIndex((s) => s.anahtar === satir.anahtar);
            yeni.splice(i, 1, ...alt);
            this.state.veri.satirlar = yeni;
        } catch (hata) {
            this.hataGoster(hata);
        }
    }

    async denetle(satir, i) {
        const denetim = satir.denetim && satir.denetim[i];
        if (!denetim) {
            return;
        }
        const eylem = await this.orm.call("atlas.finansal.rapor", "denetim_ac", [[this.raporId], denetim]);
        this.action.doAction(eylem);
    }

    kayitAc(satir) {
        if (satir.kayit) {
            this.action.doAction({ type: "ir.actions.act_window", res_model: satir.kayit.model, res_id: satir.kayit.id, views: [[false, "form"]] });
        }
    }

    // ------------------------------------------------------------------ notlar
    notAc(satir) {
        this.state.notAnahtar = satir.anahtar;
        this.state.notMetin = satir.not || "";
    }

    notIptal() {
        this.state.notAnahtar = null;
    }

    async notKaydet(satir) {
        const metin = this.state.notMetin;
        await this.orm.call("atlas.finansal.rapor", "not_kaydet", [[this.raporId], satir.anahtar, metin]);
        const yeni = this.state.veri.satirlar.map((s) => (s.anahtar === satir.anahtar ? { ...s, not: metin.trim() || null } : s));
        this.state.veri.satirlar = yeni;
        this.state.notAnahtar = null;
    }

    // ------------------------------------------------------------------ çıktılar
    async excel() {
        const eylem = await this.orm.call("atlas.finansal.rapor", "xlsx_indir", [[this.raporId], this.state.secenekler]);
        this.action.doAction(eylem);
    }

    async pdf() {
        try {
            const eylem = await this.orm.call("atlas.finansal.rapor", "pdf_indir", [[this.raporId], this.state.secenekler]);
            await this.action.doAction(eylem);
        } catch (hata) {
            this.hataGoster(hata);
        }
    }

    // ------------------------------------------------------------------ biçim
    hucre(satir, kolon, deger) {
        if (deger === null || deger === undefined || deger === false) {
            return "";
        }
        const tur = kolon.tur === "para" && satir.bicim && satir.bicim !== "para" ? satir.bicim : kolon.tur;
        if (tur === "metin") {
            return deger;
        }
        if (tur === "tarih") {
            return DateTime.fromISO(deger).toFormat("dd.MM.yyyy");
        }
        if (tur === "yuzde") {
            return "%" + new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(deger);
        }
        if (tur === "oran") {
            return oranBicim.format(deger);
        }
        if (tur === "gun") {
            return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 }).format(deger) + " " + _t("gün");
        }
        if (tur === "doviz") {
            return sayiBicim.format(deger) + (satir.para ? " " + satir.para : "");
        }
        return sayiBicim.format(deger);
    }

    hucreSinifi(satir, kolon, deger, i) {
        const sinif = ["text-nowrap"];
        if (!["metin", "tarih"].includes(kolon.tur)) {
            sinif.push("text-end");
        }
        if (satir.denetim && satir.denetim[i]) {
            sinif.push("o_atlas_fr_denetim");
        }
        if (typeof deger === "number" && deger < 0 && kolon.tur !== "yuzde") {
            sinif.push("o_atlas_fr_negatif");
        }
        return sinif.join(" ");
    }

    satirSinifi(satir) {
        return [`o_atlas_fr_${satir.sinif}`, satir.uyari ? "text-danger fw-bold" : "", satir.acilabilir ? "o_atlas_fr_acilabilir" : ""].join(" ");
    }

    girinti(satir) {
        return `padding-left: ${0.5 + 1.2 * ((satir.seviye || 0) + (satir.girinti || 0))}rem`;
    }

    get donemEtiketi() {
        const s = this.state.secenekler;
        const fmt = (d) => DateTime.fromISO(d).toFormat("dd.MM.yyyy");
        return this.tekTarih ? fmt(s.tarih_bit) + " " + _t("itibarıyla") : `${fmt(s.tarih_bas)} – ${fmt(s.tarih_bit)}`;
    }
}

registry.category("actions").add("atlas_finansal.rapor", AtlasFinansalRapor);
