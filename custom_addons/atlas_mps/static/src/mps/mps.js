import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/**
 * Ana Üretim Planı tablosu: her plan satırı için dönem dönem talep, ikmal ve tahmini stok.
 * Hesap sunucuda (`atlas.mps`); burada yalnızca gösterim ve düzenleme.
 */
export class AtlasMpsEkran extends Component {
    static template = "atlas_mps.Ekran";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({ veri: null, depoId: false, yukleniyor: false, acik: {} });
        onWillStart(() => this.yukle());
    }

    async yukle() {
        this.state.yukleniyor = true;
        try {
            this.state.veri = await this.orm.call("atlas.mps", "ekran_verisi", [this.state.depoId]);
        } finally {
            this.state.yukleniyor = false;
        }
    }

    sayi(deger) {
        return formatFloat(deger || 0, { digits: [16, 2] }).replace(/,00$/, "");
    }

    hucreSinif(donem) {
        return { eksik: "o_atlas_mps_eksik", fazla: "o_atlas_mps_fazla" }[donem.durum] || "o_atlas_mps_yeterli";
    }

    detayAcik(satir) {
        return !!this.state.acik[satir.id];
    }

    detayDegistir(satir) {
        this.state.acik[satir.id] = !this.state.acik[satir.id];
    }

    async depoDegisti(ev) {
        this.state.depoId = parseInt(ev.target.value) || false;
        await this.yukle();
    }

    async degerYaz(satir, donem, alan, ev) {
        const deger = parseFloat(String(ev.target.value).replace(/\./g, "").replace(",", ".")) || 0;
        try {
            await this.orm.call("atlas.mps", "tahmin_yaz", [[satir.id], donem.tarih, alan, deger]);
        } finally {
            await this.yukle();
        }
    }

    async oneriyeDon(satir, donem) {
        await this.orm.call("atlas.mps", "oneriye_don", [[satir.id], donem.tarih]);
        await this.yukle();
    }

    async siparisVer(satirlar, donem = null) {
        const ids = satirlar.map((s) => s.id);
        const sonuc = await this.orm.call("atlas.mps", "siparis_ver", [ids, donem ? donem.tarih : false]);
        this.notification.add(sonuc.mesaj, { type: sonuc.sonuc === "ok" ? "success" : "warning" });
        await this.yukle();
    }

    tumunuSiparisEt() {
        return this.siparisVer(this.state.veri.satirlar);
    }

    planEkle() {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "atlas.mps",
                views: [[false, "form"]],
                target: "new",
                name: "Plana Ürün Ekle",
                context: this.state.depoId ? { default_warehouse_id: this.state.depoId } : {},
            },
            { onClose: () => this.yukle() }
        );
    }

    planDuzenle(satir) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "atlas.mps",
                res_id: satir.id,
                views: [[false, "form"]],
                target: "new",
                name: satir.urun,
            },
            { onClose: () => this.yukle() }
        );
    }

    urunAc(satir) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.product",
            res_id: satir.urun_id,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("atlas_mps.ekran", AtlasMpsEkran);
