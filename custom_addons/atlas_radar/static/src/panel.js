import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const ACIK = ["yeni", "inceleniyor", "onaylandi"];

export class AtlasRadarPanel extends Component {
    static template = "atlas_radar.Panel";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ veri: null });
        onWillStart(() => this.yukle());
    }

    async yukle() {
        this.state.veri = await this.orm.call("atlas.radar.degisiklik", "panel_verisi", []);
    }

    get kartlar() {
        const k = this.state.veri.kpi;
        const bugun = luxon.DateTime.local();
        return [
            { ad: _t("Yeni"), sayi: k.yeni, sinif: "text-primary", alan: [["durum", "=", "yeni"]] },
            { ad: _t("İnceleniyor"), sayi: k.inceleniyor, sinif: "text-info", alan: [["durum", "=", "inceleniyor"]] },
            { ad: _t("Aksiyon Gerekli"), sayi: k.aksiyon, sinif: "text-warning", alan: [["durum", "=", "onaylandi"]] },
            { ad: _t("Yüksek / Kritik Açık"), sayi: k.kritik, sinif: "text-danger",
              alan: [["durum", "in", ACIK], ["onem", "in", ["yuksek", "kritik"]]] },
            { ad: _t("Kırıcı Değişiklik"), sayi: k.kirici, sinif: "text-danger", alan: [["durum", "in", ACIK], ["kirici", "=", true]] },
            { ad: _t("30 Günde Yürürlük"), sayi: k.yaklasan, sinif: "text-warning",
              alan: [["durum", "in", ACIK], ["yururluk_tarihi", ">=", bugun.toISODate()],
                     ["yururluk_tarihi", "<=", bugun.plus({ days: 30 }).toISODate()]] },
            { ad: _t("Son 7 Gün"), sayi: k.hafta, sinif: "text-body",
              alan: [["tespit_tarihi", ">=", bugun.minus({ days: 7 }).toFormat("yyyy-MM-dd HH:mm:ss")], ["durum", "!=", "mukerrer"]] },
            { ad: _t("Sorunlu Kaynak"), sayi: k.sorunlu_kaynak, sinif: k.sorunlu_kaynak ? "text-danger" : "text-success", kaynak: true },
        ];
    }

    onemSinif(onem) {
        return { kritik: "text-bg-danger", yuksek: "text-bg-warning", orta: "text-bg-info", dusuk: "text-bg-light" }[onem];
    }

    saglikSinif(saglik) {
        return { iyi: "text-bg-success", uyari: "text-bg-warning", hata: "text-bg-danger", robots: "text-bg-danger",
                 bekliyor: "text-bg-light", pasif: "text-bg-secondary" }[saglik];
    }

    tarih(metin) {
        return metin ? luxon.DateTime.fromSQL(metin, { zone: "utc" }).setZone("default").toFormat("dd.MM.yyyy HH:mm") : "";
    }

    gun(metin) {
        return metin ? luxon.DateTime.fromISO(metin).toFormat("dd.MM.yyyy") : "";
    }

    kalanGun(metin) {
        if (!metin) {
            return "";
        }
        const fark = Math.round(luxon.DateTime.fromISO(metin).diff(luxon.DateTime.local().startOf("day"), "days").days);
        return fark === 0 ? _t("bugün") : fark > 0 ? _t("%s gün kaldı", fark) : _t("%s gün geçti", -fark);
    }

    kartAc(kart) {
        if (kart.kaynak) {
            return this.action.doAction("atlas_radar.action_kaynak", { additionalContext: { search_default_sorunlu: 1 } });
        }
        this.action.doAction({
            type: "ir.actions.act_window", name: kart.ad, res_model: "atlas.radar.degisiklik",
            views: [[false, "list"], [false, "kanban"], [false, "form"]], domain: kart.alan,
        });
    }

    kategoriAc(k) {
        this.action.doAction({
            type: "ir.actions.act_window", name: k.ad, res_model: "atlas.radar.degisiklik",
            views: [[false, "list"], [false, "form"]], domain: [["durum", "in", ACIK], ["kategori_id", "=", k.id || false]],
        });
    }

    ac(model, id) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: model, res_id: id, views: [[false, "form"]] });
    }

    git(xmlid) {
        this.action.doAction(xmlid);
    }
}

registry.category("actions").add("atlas_radar.panel", AtlasRadarPanel);
