import { Component, markup, onWillDestroy, onWillStart, proxy, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const KEY = "atlas_shopfloor";

function oku() {
    try {
        return JSON.parse(browser.localStorage.getItem(KEY) || "{}");
    } catch {
        return {};
    }
}

/** Üretim alanı operatör ekranı (tablet). İş mantığı `atlas.shopfloor` modelinde. */
export class AtlasShopfloor extends Component {
    static template = "atlas_shopfloor.App";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const kayit = oku();
        this.state = proxy({
            ekran: "merkez",
            merkezler: [],
            operatorler: [],
            merkez: kayit.merkez || null,
            operator: kayit.operator || null,
            liste: null,
            wo: null,
            yuklenme: 0,
            simdi: Date.now(),
            pinIcin: null,
            pin: "",
            panel: null, // hurda | sorun | durus | miktar
            form: {},
            yukleniyor: false,
        });
        this.zamanlayici = browser.setInterval(() => (this.state.simdi = Date.now()), 1000);
        onWillDestroy(() => browser.clearInterval(this.zamanlayici));
        onWillStart(async () => {
            this.state.merkezler = await this.cagir("merkezler", []);
            if (this.state.merkez && this.state.operator) {
                await this.listeAc();
            } else if (this.state.merkez) {
                await this.operatorEkrani();
            }
        });
    }

    async cagir(method, args) {
        this.state.yukleniyor = true;
        try {
            return await this.orm.call("atlas.shopfloor", method, args);
        } catch (error) {
            this.notification.add(error.data?.message || error.message || String(error), { type: "danger" });
            throw error;
        } finally {
            this.state.yukleniyor = false;
        }
    }

    kaydet() {
        try {
            browser.localStorage.setItem(KEY, JSON.stringify({ merkez: this.state.merkez, operator: this.state.operator }));
        } catch {
            // depolama kapalı
        }
    }

    bildir(sonuc) {
        this.notification.add(sonuc.mesaj, { type: sonuc.sonuc === "ok" ? "success" : "warning" });
    }

    // ------------------------------------------------------------ gezinme
    async merkezEkrani() {
        this.state.merkezler = await this.cagir("merkezler", []);
        Object.assign(this.state, { ekran: "merkez", wo: null, liste: null, panel: null });
    }

    async merkezSec(m) {
        this.state.merkez = { id: m.id, ad: m.ad };
        this.kaydet();
        if (this.state.operator) {
            await this.listeAc();
        } else {
            await this.operatorEkrani();
        }
    }

    async operatorEkrani() {
        this.state.operatorler = await this.cagir("operatorler", []);
        Object.assign(this.state, { ekran: "operator", pinIcin: null, pin: "" });
    }

    async operatorSec(o) {
        if (o.pin) {
            Object.assign(this.state, { pinIcin: o, pin: "" });
            return;
        }
        await this.operatorOnayla(o, "");
    }

    async operatorOnayla(o, pin) {
        try {
            const sonuc = await this.cagir("operator_dogrula", [o.id, pin]);
            this.state.operator = { id: sonuc.id, ad: sonuc.ad };
            this.kaydet();
            await this.listeAc();
        } catch {
            this.state.pin = "";
        }
    }

    pinTus(t) {
        if (t === "sil") {
            this.state.pin = this.state.pin.slice(0, -1);
        } else if (t === "ok") {
            this.operatorOnayla(this.state.pinIcin, this.state.pin);
        } else if (this.state.pin.length < 8) {
            this.state.pin += t;
        }
    }

    pinVazgec() {
        this.state.pinIcin = null;
    }

    durusSecili(l) {
        return String(this.state.form.loss_id) === String(l.id);
    }

    durusSec(l) {
        this.state.form.loss_id = l.id;
    }

    cikisYap() {
        this.state.operator = null;
        this.kaydet();
        this.operatorEkrani();
    }

    async listeAc() {
        this.state.liste = await this.cagir("is_emirleri", [this.state.merkez.id]);
        Object.assign(this.state, { ekran: "liste", wo: null, panel: null });
    }

    async woAc(id) {
        this.woYukle(await this.cagir("is_emri_ac", [id]));
        Object.assign(this.state, { ekran: "wo", panel: null });
    }

    woYukle(wo) {
        wo.talimat = wo.talimat ? markup(wo.talimat) : "";
        this.state.wo = wo;
        this.state.yuklenme = Date.now();
    }

    async geri() {
        if (this.state.ekran === "wo") {
            await this.listeAc();
        } else if (this.state.ekran === "liste") {
            await this.merkezEkrani();
        } else if (this.state.ekran === "operator") {
            await this.merkezEkrani();
        }
    }

    // ------------------------------------------------------------ süre
    get gecenDk() {
        const wo = this.state.wo;
        if (!wo) {
            return 0;
        }
        const ek = wo.calisiyor ? (this.state.simdi - this.state.yuklenme) / 60000 : 0;
        return wo.gecen_dk + ek;
    }

    sure(dk) {
        const toplam = Math.max(0, Math.round((dk || 0) * 60));
        const s = Math.floor(toplam / 3600);
        const d = Math.floor((toplam % 3600) / 60);
        const sn = toplam % 60;
        return `${String(s).padStart(2, "0")}:${String(d).padStart(2, "0")}:${String(sn).padStart(2, "0")}`;
    }

    get ilerleme() {
        const wo = this.state.wo;
        if (!wo || !wo.planlanan_dk) {
            return 0;
        }
        return Math.min(100, Math.round((100 * this.gecenDk) / wo.planlanan_dk));
    }

    // ------------------------------------------------------------ işlemler
    async baslat() {
        this.woYukle(await this.cagir("baslat", [this.state.wo.id, this.state.operator.id]));
    }

    async duraklat() {
        this.woYukle(await this.cagir("duraklat", [this.state.wo.id]));
    }

    panelAc(panel) {
        const wo = this.state.wo;
        const form = {
            miktar: { uretilen: wo.uretiliyor, hatali: wo.hatali },
            hurda: { product_id: wo.hurda_urunleri[0]?.id || null, miktar: 1, neden: "" },
            sorun: { baslik: "", aciklama: "" },
            durus: { loss_id: this.state.liste?.kayip_nedenleri?.[0]?.id || null, aciklama: "" },
        }[panel];
        Object.assign(this.state, { panel, form });
    }

    panelKapat() {
        this.state.panel = null;
    }

    deger(alan, ev) {
        this.state.form[alan] = ev.target.value;
    }

    async miktarKaydet(bitir = false) {
        const f = this.state.form;
        const args = [this.state.wo.id, parseFloat(f.uretilen) || 0, parseFloat(f.hatali) || 0];
        this.woYukle(await this.cagir(bitir ? "bitir" : "miktar_yaz", args));
        this.state.panel = null;
        if (bitir) {
            this.notification.add("İş emri bitti.", { type: "success" });
        }
    }

    async uretimiTamamla() {
        this.bildir(await this.cagir("uretimi_tamamla", [this.state.wo.id]));
        await this.listeAc();
    }

    async tuketim(b, ev) {
        const miktar = parseFloat(String(ev.target.value).replace(",", ".")) || 0;
        this.woYukle(await this.cagir("tuketim_yaz", [this.state.wo.id, b.id, miktar]));
    }

    async hurdaKaydet() {
        const f = this.state.form;
        const secili = this.hurdaUrunleri.find((u) => String(u.id) === String(f.product_id)) || this.hurdaUrunleri[0];
        this.bildir(await this.cagir("hurda", [this.state.wo.id, secili.id, parseFloat(f.miktar) || 0, f.neden || ""]));
        this.state.panel = null;
        await this.woAc(this.state.wo.id);
    }

    get hurdaUrunleri() {
        return this.state.wo ? this.state.wo.hurda_urunleri || [] : [];
    }

    async sorunKaydet() {
        const f = this.state.form;
        this.bildir(await this.cagir("sorun_bildir", [this.state.wo.id, f.baslik, f.aciklama, this.state.operator?.id || false]));
        this.state.panel = null;
    }

    async durusKaydet() {
        const f = this.state.form;
        this.bildir(await this.cagir("durus_bildir", [this.state.merkez.id, parseInt(f.loss_id), f.aciklama, this.state.operator?.id || false]));
        this.state.panel = null;
        await (this.state.ekran === "wo" ? this.woAc(this.state.wo.id) : this.listeAc());
    }

    async durusBitir() {
        this.bildir(await this.cagir("durus_bitir", [this.state.merkez.id]));
        await (this.state.ekran === "wo" ? this.woAc(this.state.wo.id) : this.listeAc());
    }

    get merkezDurusta() {
        return (this.state.wo?.merkez?.durum || this.state.liste?.merkez?.durum) === "blocked";
    }

    async kalite(k, islem, ev) {
        const degerler = {};
        if (k.tip === "olcum") {
            degerler.olcum = this.state.form[`olcum_${k.id}`];
        }
        this.bildir(await this.cagir("kalite_sonuc", [k.id, islem, degerler]));
        await this.woAc(this.state.wo.id);
    }

    kaliteFormAc(k) {
        this.action.doAction(
            { type: "ir.actions.act_window", res_model: "atlas.kalite.kontrol", res_id: k.id, views: [[false, "form"]], target: "new" },
            { onClose: () => this.woAc(this.state.wo.id) }
        );
    }

    kaliteDeger(k, ev) {
        this.state.form[`olcum_${k.id}`] = ev.target.value;
    }

    cikis() {
        window.location.href = "/odoo";
    }
}

registry.category("actions").add("atlas_shopfloor.app", AtlasShopfloor);
