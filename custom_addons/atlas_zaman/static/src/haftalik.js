import { Component, onWillDestroy, onWillStart, proxy, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const { DateTime } = luxon;
const MODEL = "account.analytic.line";

/** "1:30", "1,5", "1.5", "90m" → saat (ondalık) */
export function saatOku(metin) {
    const m = String(metin ?? "").trim().toLowerCase().replace(",", ".");
    if (!m) {
        return 0;
    }
    if (m.includes(":")) {
        const [s, d] = m.split(":");
        return (parseInt(s || "0", 10) || 0) + (parseInt(d || "0", 10) || 0) / 60;
    }
    if (m.endsWith("m")) {
        return (parseFloat(m) || 0) / 60;
    }
    const sayi = parseFloat(m);
    return Number.isFinite(sayi) ? sayi : NaN;
}

/** 1.5 → "1:30" */
export function saatYaz(saat) {
    if (!saat) {
        return "";
    }
    const toplamDk = Math.round(saat * 60);
    const s = Math.floor(toplamDk / 60);
    const d = toplamDk % 60;
    return `${s}:${String(d).padStart(2, "0")}`;
}

export class AtlasZamanHaftalik extends Component {
    static template = "atlas_zaman.Haftalik";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.state = proxy({
            hafta: DateTime.local().startOf("week"),
            veri: null,
            calisanId: null,
            yeniProje: "",
            yeniGorev: "",
            simdi: Date.now(),
            kaydediliyor: 0,
        });
        this.zamanlayici = browser.setInterval(() => (this.state.simdi = Date.now()), 1000);
        onWillDestroy(() => browser.clearInterval(this.zamanlayici));
        onWillStart(() => this.yukle());
    }

    async yukle() {
        try {
            this.state.veri = await this.orm.call(MODEL, "atlas_haftalik", [this.state.hafta.toISODate(), this.state.calisanId]);
            this.state.calisanId = this.state.veri.calisan.id;
        } catch (hata) {
            this.hata(hata);
        }
    }

    hata(hata) {
        this.notification.add(hata.data?.message || hata.message || String(hata), { type: "danger" });
    }

    // ------------------------------------------------------------------
    // Görüntü yardımcıları
    // ------------------------------------------------------------------

    get baslik() {
        const bas = this.state.hafta;
        const bit = bas.plus({ days: 6 });
        return `${bas.toFormat("d MMM")} – ${bit.toFormat("d MMM yyyy")} · ${_t("Hafta")} ${bas.weekNumber}`;
    }

    gunEtiketi(gun) {
        return DateTime.fromISO(gun.tarih).toFormat("ccc d");
    }

    hucreDegeri(satir, gun) {
        return saatYaz(satir.hucreler[gun.tarih].saat);
    }

    hucreKilitli(satir, gun) {
        return satir.hucreler[gun.tarih].kilitli;
    }

    hucreSinifi(satir, gun) {
        return { o_kilitli: this.hucreKilitli(satir, gun), o_bugun: gun.bugun, o_haftasonu: gun.hafta_ici >= 5 };
    }

    satirToplami(satir) {
        return saatYaz(Object.values(satir.hucreler).reduce((t, h) => t + h.saat, 0)) || "0:00";
    }

    gunToplamiSaat(gun) {
        return this.state.veri.satirlar.reduce((t, s) => t + s.hucreler[gun.tarih].saat, 0);
    }

    gunToplami(gun) {
        return saatYaz(this.gunToplamiSaat(gun)) || "0:00";
    }

    gunToplamSinifi(gun) {
        const toplam = this.gunToplamiSaat(gun);
        if (!gun.beklenen) {
            return toplam ? "text-primary" : "text-muted";
        }
        if (toplam + 0.01 < gun.beklenen) {
            return "text-danger";
        }
        return toplam > gun.beklenen + 0.01 ? "text-warning" : "text-success";
    }

    beklenen(gun) {
        return gun.beklenen ? saatYaz(gun.beklenen) : "–";
    }

    get haftaToplami() {
        return saatYaz(this.state.veri.gunler.reduce((t, g) => t + this.gunToplamiSaat(g), 0)) || "0:00";
    }

    get haftaBeklenen() {
        return saatYaz(this.state.veri.gunler.reduce((t, g) => t + g.beklenen, 0)) || "0:00";
    }

    get secilebilirGorevler() {
        const proje = parseInt(this.state.yeniProje, 10);
        return this.state.veri.gorevler.filter((g) => g.project_id === proje);
    }

    get sayacSuresi() {
        const sayac = this.state.veri?.sayac;
        if (!sayac) {
            return "";
        }
        const bas = DateTime.fromSQL(sayac.baslangic, { zone: "utc" });
        const sn = Math.max(0, Math.floor((this.state.simdi - bas.toMillis()) / 1000));
        const s = Math.floor(sn / 3600);
        const d = Math.floor((sn % 3600) / 60);
        return `${s}:${String(d).padStart(2, "0")}:${String(sn % 60).padStart(2, "0")}`;
    }

    sayacBuSatirda(satir) {
        const sayac = this.state.veri?.sayac;
        return Boolean(sayac && sayac.project_id === satir.project_id && (sayac.task_id || false) === (satir.task_id || false));
    }

    // ------------------------------------------------------------------
    // Eylemler
    // ------------------------------------------------------------------

    async kaydir(gun) {
        this.state.hafta = gun === 0 ? DateTime.local().startOf("week") : this.state.hafta.plus({ days: gun });
        await this.yukle();
    }

    async calisanSec(ev) {
        this.state.calisanId = parseInt(ev.target.value, 10);
        await this.yukle();
    }

    async hucreDegisti(ev, satir, gun) {
        const saat = saatOku(ev.target.value);
        if (Number.isNaN(saat) || saat < 0 || saat > 24) {
            this.notification.add(_t("Geçersiz süre. Örnek: 1:30 veya 1,5"), { type: "warning" });
            ev.target.value = this.hucreDegeri(satir, gun);
            return;
        }
        const hucre = satir.hucreler[gun.tarih];
        if (Math.abs(hucre.saat - saat) < 0.005) {
            ev.target.value = saatYaz(saat);
            return;
        }
        const onceki = hucre.saat;
        hucre.saat = saat;
        ev.target.value = saatYaz(saat);
        this.state.kaydediliyor++;
        try {
            await this.orm.call(MODEL, "atlas_hucre_kaydet", [this.state.calisanId, satir.project_id, satir.task_id, gun.tarih, saat]);
        } catch (hata) {
            hucre.saat = onceki;
            ev.target.value = saatYaz(onceki);
            this.hata(hata);
        } finally {
            this.state.kaydediliyor--;
        }
    }

    hucreTus(ev) {
        if (ev.key === "Enter") {
            ev.target.blur();
        }
    }

    projeSec(ev) {
        this.state.yeniProje = ev.target.value;
        this.state.yeniGorev = "";
    }

    gorevSec(ev) {
        this.state.yeniGorev = ev.target.value;
    }

    projeSecili(proje) {
        return `${proje.id}` === this.state.yeniProje;
    }

    gorevSecili(gorev) {
        return `${gorev.id}` === this.state.yeniGorev;
    }

    satirEkle() {
        const proje = this.state.veri.projeler.find((p) => p.id === parseInt(this.state.yeniProje, 10));
        if (!proje) {
            return;
        }
        const gorev = this.state.veri.gorevler.find((g) => g.id === parseInt(this.state.yeniGorev, 10));
        const anahtar = `${proje.id}_${gorev?.id || 0}`;
        if (!this.state.veri.satirlar.some((s) => s.anahtar === anahtar)) {
            const hucreler = {};
            for (const gun of this.state.veri.gunler) {
                hucreler[gun.tarih] = { saat: 0, kilitli: false };
            }
            this.state.veri.satirlar.push({
                anahtar,
                project_id: proje.id,
                project_ad: proje.ad,
                task_id: gorev?.id || false,
                task_ad: gorev?.ad || "",
                hucreler,
            });
        }
        this.state.yeniProje = "";
        this.state.yeniGorev = "";
    }

    async sayacBaslat(satir) {
        try {
            this.state.veri.sayac = await this.orm.call("atlas.zaman.sayac", "atlas_baslat", [satir.project_id, satir.task_id]);
            this.env.bus.trigger("atlas_zaman:sayac");
        } catch (hata) {
            this.hata(hata);
        }
    }

    async sayacDurdur() {
        try {
            const sayac = this.state.veri.sayac;
            const sonuc = await this.orm.call("atlas.zaman.sayac", "atlas_durdur", [[sayac.id]]);
            this.notification.add(_t("%s saat kaydedildi.", saatYaz(sonuc[0]?.saat || 0)), { type: "success" });
            this.env.bus.trigger("atlas_zaman:sayac");
            await this.yukle();
        } catch (hata) {
            this.hata(hata);
        }
    }

    async haftayiOnayla() {
        try {
            const sayi = await this.orm.call(MODEL, "atlas_hafta_onayla", [this.state.hafta.toISODate(), this.state.calisanId]);
            this.notification.add(_t("%s kayıt onaylandı.", sayi), { type: "success" });
            await this.yukle();
        } catch (hata) {
            this.hata(hata);
        }
    }

    ayrintilar() {
        const bas = this.state.hafta.toISODate();
        const bit = this.state.hafta.plus({ days: 6 }).toISODate();
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Zaman Kayıtları"),
            res_model: MODEL,
            views: [[false, "list"], [false, "form"]],
            domain: [["employee_id", "=", this.state.calisanId], ["project_id", "!=", false], ["date", ">=", bas], ["date", "<=", bit]],
            context: { is_timesheet: 1, default_employee_id: this.state.calisanId },
        });
    }
}

registry.category("actions").add("atlas_zaman.haftalik", AtlasZamanHaftalik);
