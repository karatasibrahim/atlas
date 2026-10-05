import { Component, proxy, signal, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { KeepLast } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";
import { Model, useModel } from "@web/model/model";
import { useSetupAction } from "@web/search/action_hook";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { standardViewProps } from "@web/views/standard_view_props";

const SAYISAL = ["integer", "float", "monetary"];

export class AtlasKohortArchParser {
    parse(xmlDoc, models, modelName) {
        const fields = models[modelName].fields;
        const a = (ad) => xmlDoc.getAttribute(ad);
        const olculer = [{ ad: "__count", etiket: _t("Kayıt sayısı") }];
        for (const [ad, alan] of Object.entries(fields)) {
            if (SAYISAL.includes(alan.type) && alan.store && ad !== "id" && !alan.name?.startsWith("__")) {
                olculer.push({ ad, etiket: alan.string });
            }
        }
        return {
            baslik: a("string") || "",
            dateStart: a("date_start"),
            dateStop: a("date_stop"),
            interval: a("interval") || "month",
            mode: a("mode") || "retention",
            measure: a("measure") || "__count",
            olculer,
            dateStartEtiket: fields[a("date_start")]?.string,
            dateStopEtiket: fields[a("date_stop")]?.string,
        };
    }
}

export class AtlasKohortModel extends Model {
    setup(params) {
        this.resModel = params.resModel;
        this.arch = params.archInfo;
        this.ayar = proxy({ interval: this.arch.interval, mode: this.arch.mode, measure: this.arch.measure });
        this.veri = null;
        this.keepLast = new KeepLast();
        this.searchParams = { domain: [], context: {} };
    }

    async load(searchParams) {
        if (searchParams) {
            this.searchParams = searchParams;
        }
        this.veri = await this.keepLast.add(
            this.orm.call(this.resModel, "atlas_kohort_verisi",
                [this.searchParams.domain, this.arch.dateStart, this.arch.dateStop, this.ayar.interval, this.ayar.measure, this.ayar.mode],
                { context: this.searchParams.context })
        );
        this.notify();
    }

    async ayarla(degisiklik) {
        Object.assign(this.ayar, degisiklik);
        await this.load();
    }
}

export class AtlasKohortRenderer extends Component {
    static template = "atlas_gorunum.KohortRenderer";
    props = useProps({ model: t.object(), archInfo: t.object(), hucreAc: t.function(), ayarla: t.function() });

    get veri() {
        return this.props.model.veri;
    }

    get olcuEtiketi() {
        return this.props.archInfo.olculer.find((o) => o.ad === this.props.model.ayar.measure)?.etiket || "";
    }

    sayi(v) {
        return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: this.props.model.ayar.measure === "__count" ? 0 : 2 }).format(v || 0);
    }

    yuzde(v) {
        return v === null || v === undefined ? "" : `%${new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 1 }).format(v)}`;
    }

    hucreStili(h) {
        if (!h) {
            return "";
        }
        // Elde tutmada yüksek oran koyu, kayıpta yüksek kayıp koyu
        const yogunluk = Math.max(0.06, Math.min(1, h.yuzde / 100));
        const renk = this.props.model.ayar.mode === "churn" ? "220, 53, 69" : "113, 75, 103";
        return `background-color: rgba(${renk}, ${yogunluk}); color: ${yogunluk > 0.55 ? "#fff" : "inherit"};`;
    }

    sutunlar() {
        return [...Array(this.veri?.donem_sayisi || 0).keys()];
    }
}

export class AtlasKohortController extends Component {
    static template = "atlas_gorunum.KohortView";
    static components = { Layout, CogMenu, SearchBar, AtlasKohortRenderer };
    props = useProps({
        ...standardViewProps,
        Model: t.function(),
        Renderer: t.function(),
        buttonTemplate: t.string(),
        archInfo: t.object(),
    });
    rootRef = signal.ref();

    setup() {
        this.action = useService("action");
        this.model = useModel(this.props.Model, { resModel: this.props.resModel, archInfo: this.props.archInfo });
        useSetupAction({ rootRef: this.rootRef });
        this.searchBarToggler = useSearchBarToggler();
    }

    ayarla(ev, alan) {
        this.model.ayarla({ [alan]: ev.target.value });
    }

    hucreAc(satir, hucre) {
        const { dateStart, dateStop } = this.props.archInfo;
        const alan = [...this.model.searchParams.domain, [dateStart, ">=", satir.bas], [dateStart, "<", satir.bit]];
        if (hucre) {
            if (this.model.ayar.mode === "churn") {
                alan.push([dateStop, "<", hucre.bit]);
            } else {
                alan.push("|", [dateStop, "=", false], [dateStop, ">=", hucre.bit]);
            }
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: `${this.props.archInfo.baslik || ""} — ${satir.etiket}`,
            res_model: this.props.resModel,
            domain: alan,
            views: [[false, "list"], [false, "form"]],
            context: this.model.searchParams.context,
        });
    }
}

export const atlasKohortView = {
    type: "atlas_kohort",
    display_name: _t("Kohort"),
    icon: "table_view",
    multiRecord: true,
    searchMenuTypes: ["filter", "favorite"],
    ArchParser: AtlasKohortArchParser,
    Controller: AtlasKohortController,
    Model: AtlasKohortModel,
    Renderer: AtlasKohortRenderer,
    buttonTemplate: "atlas_gorunum.KohortButtons",
    props: (props, view) => {
        const { arch, relatedModels, resModel } = props;
        return {
            ...props,
            Model: view.Model,
            Renderer: view.Renderer,
            buttonTemplate: view.buttonTemplate,
            archInfo: new view.ArchParser().parse(arch, relatedModels, resModel),
        };
    },
};

registry.category("views").add("atlas_kohort", atlasKohortView);
