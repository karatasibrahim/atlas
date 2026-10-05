import { Component, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { constants } from "@odoo/o-spreadsheet";
import { _t } from "@web/core/l10n/translation";
import { download } from "@web/core/network/download";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { SpreadsheetComponent } from "@spreadsheet/actions/spreadsheet_component";
import { OdooSpreadsheetModel } from "@spreadsheet/model";
import { OdooDataProvider } from "@spreadsheet/data_sources/odoo_data_provider";
import { waitForDataLoaded } from "@spreadsheet/helpers/model";
import { addEmptyGranularity } from "@spreadsheet/pivot/pivot_helpers";

const MODEL = "atlas.tablo";

export class AtlasTabloEditor extends Component {
    static template = "atlas_tablo.Editor";
    static components = { SpreadsheetComponent };
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ ad: "", durum: "kayitli", saltOkunur: false });
        this.zamanlayici = null;
        onWillStart(() => this.yukle());
        onWillUnmount(() => {
            if (this.model) {
                this.model.off("update", this);
            }
            clearTimeout(this.zamanlayici);
            if (this.state.durum === "degisti") {
                this.kaydet();
            }
        });
    }

    async yukle() {
        const params = this.props.action.params || {};
        let tabloId = params.tablo_id || this.props.state?.tablo_id;
        const yeniPivot = !tabloId && params.yeni_pivot;
        if (!tabloId) {
            tabloId = await this.orm.call(MODEL, "atlas_tablo_yeni", [yeniPivot ? yeniPivot.ad : false]);
        }
        this.tabloId = tabloId;
        const kayit = await this.orm.call(MODEL, "atlas_tablo_ac", [[tabloId]]);
        this.state.ad = kayit.ad;
        this.state.saltOkunur = kayit.salt_okunur;
        const odooDataProvider = new OdooDataProvider(this.env);
        // ERP verisi (pivot/liste/grafik) geldikçe hücreler yeniden hesaplanır
        odooDataProvider.addEventListener("data-source-updated", () => this.model?.dispatch("EVALUATE_CELLS"));
        this.model = new OdooSpreadsheetModel(
            kayit.veri,
            { custom: { env: this.env, odooDataProvider }, mode: kayit.salt_okunur ? "readonly" : "normal" },
            []
        );
        if (yeniPivot) {
            await this.pivotEkle(yeniPivot);
        }
        this.sonVeri = JSON.stringify(this.model.exportData());
        if (yeniPivot) {
            await this.kaydet(true);
        }
        this.props.updateActionState?.({ tablo_id: tabloId });
        this.model.on("update", this, () => this.planla());
    }

    async pivotEkle(p) {
        const alanlar = await this.orm.call(p.resModel, "fields_get", [], { attributes: ["type", "string", "aggregator", "relation", "store"] });
        const pivot = {
            type: "ODOO",
            model: p.resModel,
            domain: p.domain || [],
            context: p.context || {},
            measures: (p.activeMeasures || ["__count"]).map((m) => ({
                id: alanlar[m]?.aggregator ? `${m}:${alanlar[m].aggregator}` : m,
                fieldName: m,
                aggregator: alanlar[m]?.aggregator,
            })),
            columns: addEmptyGranularity(p.colGroupBys || [], alanlar),
            rows: addEmptyGranularity(p.rowGroupBys || [], alanlar),
            name: p.ad,
            style: { tableStyleId: constants.PIVOT_INSERT_TABLE_STYLE_ID },
        };
        const pivotId = "1";
        this.model.dispatch("ADD_PIVOT", { pivotId, pivot });
        const formulId = this.model.getters.getPivotFormulaId(pivotId);
        this.model.dispatch("UPDATE_CELL", {
            sheetId: this.model.getters.getActiveSheetId(),
            col: 0,
            row: 0,
            content: `=PIVOT(${formulId})`,
        });
    }

    planla() {
        if (this.state.saltOkunur) {
            return;
        }
        clearTimeout(this.zamanlayici);
        this.zamanlayici = setTimeout(() => this.kaydet(), 1500);
    }

    async kaydet(zorla = false) {
        if (this.state.saltOkunur || !this.model) {
            return;
        }
        const veri = JSON.stringify(this.model.exportData());
        if (!zorla && veri === this.sonVeri) {
            this.state.durum = "kayitli";
            return;
        }
        this.state.durum = "kaydediliyor";
        try {
            await this.orm.call(MODEL, "atlas_tablo_kaydet", [[this.tabloId], veri]);
            this.sonVeri = veri;
            this.state.durum = "kayitli";
        } catch (hata) {
            this.state.durum = "degisti";
            this.notification.add(hata.data?.message || _t("Tablo kaydedilemedi"), { type: "danger" });
        }
    }

    async adDegistir(ev) {
        const ad = ev.target.value.trim();
        if (!ad || ad === this.state.ad) {
            return;
        }
        this.state.ad = ad;
        await this.orm.call(MODEL, "atlas_tablo_kaydet", [[this.tabloId], JSON.stringify(this.model.exportData()), ad]);
        this.env.config.setDisplayName?.(ad);
    }

    async excel() {
        await waitForDataLoaded(this.model);
        const { files } = this.model.exportXLSX();
        await download({ url: "/atlas_tablo/xlsx", data: { veri: JSON.stringify(files), ad: this.state.ad } });
    }

    get durumMetni() {
        return { kayitli: _t("Kaydedildi"), kaydediliyor: _t("Kaydediliyor…"), degisti: _t("Kaydedilmedi") }[this.state.durum];
    }
}

registry.category("actions").add("atlas_tablo.duzenle", AtlasTabloEditor, { force: true });
