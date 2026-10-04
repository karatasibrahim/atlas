import { Component, proxy, signal, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useModel } from "@web/model/model";
import { useSetupAction } from "@web/search/action_hook";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { standardViewProps } from "@web/views/standard_view_props";
import { AtlasGanttArchParser, AtlasGanttModel, OLCEKLER } from "./gantt_model";

const { DateTime } = luxon;
const SATIR_YUKSEKLIK = 30; // px, bir şerit

export class AtlasGanttRenderer extends Component {
    static template = "atlas_gorunum.GanttRenderer";

    props = useProps({
        model: t.object(),
        archInfo: t.object(),
        openRecord: t.function(),
        createAt: t.function(),
    });

    izRef = signal.ref();

    setup() {
        this.notification = useService("notification");
        this.state = proxy({ surukle: null });
    }

    get model() {
        return this.props.model;
    }

    get sutunlar() {
        return this.model.sutunlar;
    }

    get gridSutunlari() {
        return `grid-template-columns: repeat(${this.sutunlar.length}, minmax(0, 1fr));`;
    }

    get aralikMs() {
        const { bas, bit } = this.model.aralik;
        return bit - bas;
    }

    get bugunCizgisi() {
        const { bas, bit } = this.model.aralik;
        const simdi = DateTime.local();
        if (simdi < bas || simdi >= bit) {
            return null;
        }
        return `left: ${((simdi - bas) / this.aralikMs) * 100}%;`;
    }

    satirStili(satir) {
        return `height: ${satir.seritSayisi * SATIR_YUKSEKLIK + 6}px;`;
    }

    _konum(bas, bit) {
        const aralik = this.model.aralik;
        const sol = Math.max(0, (bas - aralik.bas) / this.aralikMs);
        const sag = Math.min(1, (bit - aralik.bas) / this.aralikMs);
        return { sol: sol * 100, gen: Math.max(0.4, (sag - sol) * 100) };
    }

    cubukStili(cubuk) {
        const s = this.state.surukle;
        let { bas, bit } = cubuk;
        if (s && s.cubuk === cubuk) {
            bas = s.bas;
            bit = s.bit;
        }
        const { sol, gen } = this._konum(bas, bit);
        return `left: ${sol}%; width: ${gen}%; top: ${cubuk.serit * SATIR_YUKSEKLIK + 3}px;`;
    }

    cubukSinifi(cubuk) {
        const aralik = this.model.aralik;
        const s = this.state.surukle;
        return {
            [`o_atlas_gantt_renk_${cubuk.renk}`]: true,
            o_atlas_gantt_kesik_sol: cubuk.bas < aralik.bas,
            o_atlas_gantt_kesik_sag: cubuk.bit > aralik.bit,
            o_atlas_gantt_suruklenen: Boolean(s && s.cubuk === cubuk && s.hareket),
        };
    }

    ilerlemeStili(cubuk) {
        return `width: ${cubuk.ilerleme}%;`;
    }

    ipucu(cubuk) {
        const tarihli = this.model.alanTuru(this.props.archInfo.dateStart) === "date";
        const bicim = tarihli ? "dd.MM.yyyy" : "dd.MM.yyyy HH:mm";
        const bit = tarihli ? cubuk.bit.minus({ days: 1 }) : cubuk.bit;
        let metin = `${cubuk.ad}\n${cubuk.bas.toFormat(bicim)} → ${bit.toFormat(bicim)}`;
        if (cubuk.ilerleme !== null) {
            metin += `\n${_t("İlerleme")}: %${Math.round(cubuk.ilerleme)}`;
        }
        return metin;
    }

    satirEtiketi(satir) {
        return `${satir.ad} (${satir.cubuklar.length})`;
    }

    // ------------------------------------------------------------------
    // Sürükle bırak
    // ------------------------------------------------------------------

    onCubukBas(ev, cubuk, satir, mod) {
        if (ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const iz = ev.target.closest(".o_atlas_gantt_iz");
        this.state.surukle = {
            cubuk,
            satir,
            mod: this.props.archInfo.canEdit ? mod : "yok",
            x0: ev.clientX,
            y0: ev.clientY,
            genislik: iz.getBoundingClientRect().width,
            bas: cubuk.bas,
            bit: cubuk.bit,
            hedef: satir,
            hareket: false,
        };
        const tasi = (e) => this.onTasi(e);
        const birak = async (e) => {
            window.removeEventListener("pointermove", tasi);
            window.removeEventListener("pointerup", birak);
            await this.onBirak(e);
        };
        window.addEventListener("pointermove", tasi);
        window.addEventListener("pointerup", birak);
    }

    onTasi(ev) {
        const s = this.state.surukle;
        if (!s || s.mod === "yok") {
            return;
        }
        const dx = ev.clientX - s.x0;
        if (!s.hareket && Math.abs(dx) < 4 && Math.abs(ev.clientY - s.y0) < 4) {
            return;
        }
        s.hareket = true;
        const fark = (dx / s.genislik) * this.aralikMs;
        if (s.mod === "tasi") {
            const bas = this.model.yuvarla(s.cubuk.bas.plus(fark));
            s.bas = bas;
            s.bit = bas.plus(s.cubuk.bit - s.cubuk.bas);
            const alt = document.elementFromPoint(ev.clientX, ev.clientY)?.closest("[data-satir]");
            if (alt) {
                s.hedef = this.model.satirlar[Number(alt.dataset.satir)] || s.satir;
            }
        } else {
            const bit = this.model.yuvarla(s.cubuk.bit.plus(fark));
            s.bit = bit > s.cubuk.bas ? bit : s.cubuk.bit;
        }
    }

    async onBirak() {
        const s = this.state.surukle;
        if (!s) {
            return;
        }
        if (!s.hareket) {
            this.state.surukle = null;
            this.props.openRecord(s.cubuk.id);
            return;
        }
        try {
            await this.model.cubukGuncelle(s.cubuk, s.bas, s.bit, s.hedef !== s.satir ? s.hedef : null);
        } catch (hata) {
            this.notification.add(hata.data?.message || hata.message || String(hata), { type: "danger" });
        } finally {
            this.state.surukle = null;
        }
    }

    hedefMi(satir) {
        const s = this.state.surukle;
        return Boolean(s && s.hareket && s.mod === "tasi" && s.hedef === satir && s.hedef !== s.satir);
    }

    onHucre(satir, sutun) {
        if (this.props.archInfo.canCreate) {
            this.props.createAt(satir, sutun);
        }
    }
}

export class AtlasGanttController extends Component {
    static template = "atlas_gorunum.GanttView";
    static components = { Layout, CogMenu, SearchBar, AtlasGanttRenderer };

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
        this.olcekler = Object.entries(OLCEKLER).map(([anahtar, o]) => ({ anahtar, ad: o.ad }));
        this.model = useModel(this.props.Model, {
            resModel: this.props.resModel,
            fields: this.props.fields,
            archInfo: this.props.archInfo,
            state: this.props.state?.modelState,
        });
        useSetupAction({
            rootRef: this.rootRef,
            getLocalState: () => ({ modelState: this.model.exportState() }),
        });
        this.searchBarToggler = useSearchBarToggler();
    }

    openRecord(resId) {
        const resIds = [...new Set(this.model.satirlar.flatMap((s) => s.cubuklar.map((c) => c.id)))];
        this.props.selectRecord(resId, { activeIds: resIds });
    }

    async createAt(satir, sutun) {
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: _t("Yeni Kayıt"),
                res_model: this.props.resModel,
                views: [[false, "form"]],
                target: "new",
                context: { ...this.props.context, ...this.model.yeniKayitBaglami(satir, sutun) },
            },
            { onClose: () => this.model.load() }
        );
    }

    async yeni() {
        const simdi = DateTime.local().startOf("hour");
        await this.createAt(null, { bas: simdi, bit: simdi.plus({ hours: 1 }) });
    }
}

export const atlasGanttView = {
    type: "atlas_gantt",
    display_name: _t("Gantt"),
    icon: "view_timeline",
    multiRecord: true,
    searchMenuTypes: ["filter", "groupBy", "favorite"],
    ArchParser: AtlasGanttArchParser,
    Controller: AtlasGanttController,
    Model: AtlasGanttModel,
    Renderer: AtlasGanttRenderer,
    buttonTemplate: "atlas_gorunum.GanttButtons",
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

registry.category("views").add("atlas_gantt", atlasGanttView);
