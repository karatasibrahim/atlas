import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/**
 * Haftalık vardiya planı (çalışan × gün) ve iş merkezi doluluğu.
 * Veri ve kurallar sunucuda (`atlas.planlama.vardiya`).
 */
export class AtlasPlanlamaHafta extends Component {
    static template = "atlas_planlama.Hafta";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const mod = this.props.action?.context?.mod === "doluluk" ? "doluluk" : "plan";
        this.state = proxy({ mod, veri: null, doluluk: null, haftaBasi: false, rolId: false, yukleniyor: false });
        this.surukle = null;
        onWillStart(() => this.yukle());
    }

    async yukle() {
        this.state.yukleniyor = true;
        try {
            const veri = await this.orm.call("atlas.planlama.vardiya", "hafta_verisi", [this.state.haftaBasi, this.state.rolId]);
            this.state.veri = veri;
            this.state.haftaBasi = veri.hafta_basi;
            if (this.state.mod === "doluluk") {
                this.state.doluluk = await this.orm.call("atlas.planlama.vardiya", "doluluk_verisi", [this.state.haftaBasi]);
            }
        } finally {
            this.state.yukleniyor = false;
        }
    }

    haftaKaydir(gun) {
        const d = new Date(this.state.haftaBasi + "T00:00:00");
        d.setDate(d.getDate() + gun);
        this.state.haftaBasi = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
        return this.yukle();
    }

    buHafta() {
        this.state.haftaBasi = false;
        return this.yukle();
    }

    modDegistir(mod) {
        this.state.mod = mod;
        return this.yukle();
    }

    rolDegisti(ev) {
        this.state.rolId = parseInt(ev.target.value) || false;
        return this.yukle();
    }

    saat(deger) {
        const s = Math.floor(deger || 0);
        const dk = Math.round(((deger || 0) - s) * 60);
        return `${s}:${String(dk).padStart(2, "0")}`;
    }

    kartSinif(kart) {
        return `o_atlas_kart o_atlas_renk_${kart.renk % 12} ${kart.durum === "taslak" ? "o_atlas_taslak" : ""}`;
    }

    gunIzinli(satir, i) {
        return satir.izinli.includes(i);
    }

    async sablonSecildi(satir, gun, ev) {
        const sablonId = parseInt(ev.target.value);
        ev.target.value = "";
        if (!sablonId) {
            return;
        }
        await this.orm.call("atlas.planlama.vardiya", "hizli_olustur", [satir.id, gun.tarih, sablonId]);
        await this.yukle();
    }

    vardiyaAc(kart) {
        this.action.doAction(
            { type: "ir.actions.act_window", res_model: "atlas.planlama.vardiya", res_id: kart.id, views: [[false, "form"]], target: "new" },
            { onClose: () => this.yukle() }
        );
    }

    yeniVardiya() {
        this.action.doAction(
            { type: "ir.actions.act_window", res_model: "atlas.planlama.vardiya", views: [[false, "form"]], target: "new" },
            { onClose: () => this.yukle() }
        );
    }

    dragStart(kart) {
        this.surukle = kart.id;
    }

    async birak(satir, gun, ev) {
        ev.preventDefault();
        const id = this.surukle;
        this.surukle = null;
        if (!id) {
            return;
        }
        await this.orm.call("atlas.planlama.vardiya", "tasi", [[id], satir.id, gun.tarih]);
        await this.yukle();
    }

    async yayinla() {
        const mesaj = await this.orm.call("atlas.planlama.vardiya", "hafta_yayinla", [this.state.haftaBasi, this.state.rolId]);
        this.notification.add(mesaj, { type: "success" });
        await this.yukle();
    }

    async oncekiHafta() {
        const mesaj = await this.orm.call("atlas.planlama.vardiya", "onceki_haftayi_kopyala", [this.state.haftaBasi]);
        this.notification.add(mesaj, { type: "info" });
        await this.yukle();
    }

    dolulukSinif(hucre) {
        return { asiri: "o_atlas_asiri", uygun: "o_atlas_uygun" }[hucre.durum] || "";
    }
}

registry.category("actions").add("atlas_planlama.hafta", AtlasPlanlamaHafta);
