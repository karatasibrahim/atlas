import { Component, onMounted, onPatched, onWillUnmount, proxy, signal, t, useProps } from "@odoo/owl";
import { loadCSS, loadJS } from "@web/core/assets";
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

const LEAFLET = "/atlas_gorunum/static/lib/leaflet";

export class AtlasHaritaArchParser {
    parse(xmlDoc, models, modelName) {
        const fields = models[modelName].fields;
        const a = (ad) => xmlDoc.getAttribute(ad);
        const ekAlanlar = [...xmlDoc.querySelectorAll("field")].map((n) => ({
            ad: n.getAttribute("name"),
            etiket: n.getAttribute("string") || fields[n.getAttribute("name")]?.string,
        }));
        const info = { partner: a("partner"), lat: a("lat"), lng: a("lng"), label: a("label") || "display_name", ekAlanlar };
        info.fieldNames = [
            ...new Set(["display_name", info.partner, info.lat, info.lng, info.label, ...ekAlanlar.map((e) => e.ad)].filter((f) => f && fields[f])),
        ];
        return info;
    }
}

function degerMetni(deger) {
    if (Array.isArray(deger)) {
        return deger[1];
    }
    if (deger && typeof deger === "object") {
        return deger.display_name;
    }
    return deger === false || deger === null || deger === undefined ? "" : String(deger);
}

export class AtlasHaritaModel extends Model {
    setup(params) {
        this.resModel = params.resModel;
        this.fields = params.fields;
        this.arch = params.archInfo;
        this.kayitlar = [];
        this.konumsuz = [];
        this.keepLast = new KeepLast();
        this.searchParams = { domain: [], context: {} };
    }

    async load(searchParams) {
        if (searchParams) {
            this.searchParams = searchParams;
        }
        const kayitlar = await this.keepLast.add(
            this.orm.searchRead(this.resModel, this.searchParams.domain, this.arch.fieldNames, {
                context: this.searchParams.context,
                limit: 1000,
            })
        );
        const { partner, lat, lng, label } = this.arch;
        let partnerler = {};
        if (partner) {
            const idler = [...new Set(kayitlar.map((k) => (Array.isArray(k[partner]) ? k[partner][0] : k[partner]?.id || k[partner])).filter(Boolean))];
            if (idler.length) {
                const okunan = await this.orm.read("res.partner", idler, ["display_name", "partner_latitude", "partner_longitude", "contact_address"]);
                partnerler = Object.fromEntries(okunan.map((p) => [p.id, p]));
            }
        }
        this.kayitlar = kayitlar.map((k) => {
            let enlem = lat ? k[lat] : null;
            let boylam = lng ? k[lng] : null;
            let adres = "";
            let partnerId = null;
            if (partner) {
                partnerId = Array.isArray(k[partner]) ? k[partner][0] : k[partner]?.id || k[partner] || null;
                const p = partnerler[partnerId];
                if (p) {
                    enlem = p.partner_latitude;
                    boylam = p.partner_longitude;
                    adres = (p.contact_address || "").replace(/\n+/g, ", ").replace(/^, |, $/g, "");
                }
            }
            return {
                id: k.id,
                ad: degerMetni(k[label]) || k.display_name,
                adres,
                partnerId,
                konum: enlem || boylam ? [enlem, boylam] : null,
                ekler: this.arch.ekAlanlar.map((e) => ({ etiket: e.etiket, deger: degerMetni(k[e.ad]) })).filter((e) => e.deger),
            };
        });
        this.konumsuz = this.kayitlar.filter((k) => !k.konum);
        this.notify();
    }

    get konumluKayitlar() {
        return this.kayitlar.filter((k) => k.konum);
    }

    async konumlariBul() {
        const partnerIdleri = [...new Set(this.konumsuz.map((k) => k.partnerId).filter(Boolean))];
        if (!partnerIdleri.length) {
            return 0;
        }
        await this.orm.call("res.partner", "geo_localize", [partnerIdleri]);
        await this.load();
        return partnerIdleri.length;
    }
}

export class AtlasHaritaRenderer extends Component {
    static template = "atlas_gorunum.HaritaRenderer";

    props = useProps({
        model: t.object(),
        archInfo: t.object(),
        openRecord: t.function(),
    });

    haritaRef = signal.ref();

    setup() {
        this.notification = useService("notification");
        this.state = proxy({ secili: null, yukleniyor: false });
        this.isaretler = new Map();
        onMounted(async () => {
            await Promise.all([loadJS(`${LEAFLET}/leaflet.js`), loadCSS(`${LEAFLET}/leaflet.css`)]);
            this.haritaKur();
        });
        onPatched(() => this.isaretleriGuncelle());
        onWillUnmount(() => this.harita?.remove());
    }

    get model() {
        return this.props.model;
    }

    haritaKur() {
        const L = window.L;
        L.Icon.Default.imagePath = `${LEAFLET}/images/`;
        this.harita = L.map(this.haritaRef(), { zoomControl: true }).setView([39.0, 35.2], 6);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
        }).addTo(this.harita);
        this.katman = L.featureGroup().addTo(this.harita);
        this.isaretleriGuncelle(true);
    }

    isaretleriGuncelle(sigdir = true) {
        if (!this.harita) {
            return;
        }
        const L = window.L;
        const imza = this.model.konumluKayitlar.map((k) => `${k.id}:${k.konum}`).join("|");
        if (imza === this.sonImza) {
            return;
        }
        this.sonImza = imza;
        this.katman.clearLayers();
        this.isaretler.clear();
        // Aynı konumdaki kayıtlar tek işarette toplanır
        const konumlar = new Map();
        for (const kayit of this.model.konumluKayitlar) {
            const anahtar = kayit.konum.join(",");
            if (!konumlar.has(anahtar)) {
                konumlar.set(anahtar, []);
            }
            konumlar.get(anahtar).push(kayit);
        }
        for (const kayitlar of konumlar.values()) {
            const isaret = L.marker(kayitlar[0].konum).addTo(this.katman);
            isaret.bindPopup(() => this.acilirIcerik(kayitlar), { minWidth: 220 });
            if (kayitlar.length > 1) {
                isaret.bindTooltip(String(kayitlar.length), { permanent: true, direction: "top", className: "o_atlas_harita_sayi" });
            }
            for (const kayit of kayitlar) {
                this.isaretler.set(kayit.id, isaret);
            }
        }
        if (sigdir && this.katman.getLayers().length) {
            this.harita.fitBounds(this.katman.getBounds().pad(0.2), { maxZoom: 14 });
        }
    }

    acilirIcerik(kayitlar) {
        const kutu = document.createElement("div");
        kutu.className = "o_atlas_harita_popup";
        for (const kayit of kayitlar) {
            const blok = document.createElement("div");
            blok.className = "o_atlas_harita_popup_kayit";
            const baslik = document.createElement("a");
            baslik.href = "#";
            baslik.className = "fw-bold d-block";
            baslik.textContent = kayit.ad;
            baslik.addEventListener("click", (ev) => {
                ev.preventDefault();
                this.props.openRecord(kayit.id);
            });
            blok.appendChild(baslik);
            for (const satir of [kayit.adres, ...kayit.ekler.map((e) => `${e.etiket}: ${e.deger}`)]) {
                if (satir) {
                    const s = document.createElement("div");
                    s.className = "text-muted small";
                    s.textContent = satir;
                    blok.appendChild(s);
                }
            }
            kutu.appendChild(blok);
        }
        return kutu;
    }

    sec(kayit) {
        this.state.secili = kayit.id;
        const isaret = this.isaretler.get(kayit.id);
        if (isaret) {
            this.harita.flyTo(isaret.getLatLng(), Math.max(this.harita.getZoom(), 13), { duration: 0.6 });
            isaret.openPopup();
        }
    }

    kayitSinifi(kayit) {
        return { o_secili: this.state.secili === kayit.id, o_konumsuz: !kayit.konum };
    }

    async konumlariBul() {
        this.state.yukleniyor = true;
        try {
            const sayi = await this.model.konumlariBul();
            const kalan = this.model.konumsuz.length;
            this.notification.add(
                kalan
                    ? _t("%(sayi)s adres arandı; %(kalan)s kaydın konumu bulunamadı (adresi eksik olabilir).", { sayi, kalan })
                    : _t("Tüm konumlar bulundu."),
                { type: kalan ? "warning" : "success" }
            );
        } catch (hata) {
            this.notification.add(hata.data?.message || hata.message || String(hata), { type: "danger" });
        } finally {
            this.state.yukleniyor = false;
        }
    }
}

export class AtlasHaritaController extends Component {
    static template = "atlas_gorunum.HaritaView";
    static components = { Layout, CogMenu, SearchBar, AtlasHaritaRenderer };

    props = useProps({
        ...standardViewProps,
        Model: t.function(),
        Renderer: t.function(),
        buttonTemplate: t.string(),
        archInfo: t.object(),
    });

    rootRef = signal.ref();

    setup() {
        this.model = useModel(this.props.Model, {
            resModel: this.props.resModel,
            fields: this.props.fields,
            archInfo: this.props.archInfo,
        });
        useSetupAction({ rootRef: this.rootRef });
        this.searchBarToggler = useSearchBarToggler();
    }

    openRecord(resId) {
        this.props.selectRecord(resId, { activeIds: this.model.kayitlar.map((k) => k.id) });
    }
}

export const atlasHaritaView = {
    type: "atlas_harita",
    display_name: _t("Harita"),
    icon: "map",
    multiRecord: true,
    searchMenuTypes: ["filter", "favorite"],
    ArchParser: AtlasHaritaArchParser,
    Controller: AtlasHaritaController,
    Model: AtlasHaritaModel,
    Renderer: AtlasHaritaRenderer,
    buttonTemplate: "atlas_gorunum.HaritaButtons",
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

registry.category("views").add("atlas_harita", atlasHaritaView);
