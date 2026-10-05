import { Component, onMounted, onWillStart, onWillUnmount, proxy, signal, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { hataMetni, RENKLER, SIMGELER, simgeCiz, simgeGecerli } from "./arac";
import { AtlasStudioEditor } from "./editor/editor";

const GORSEL = ["form", "list", "search"];

export const SEKMELER = [
    { k: "gorunumler", ad: "Görünümler" },
    { k: "raporlar", ad: "Raporlar" },
    { k: "otomasyonlar", ad: "Otomasyonlar" },
    { k: "aksiyonlar", ad: "Aksiyonlar" },
    { k: "webhooklar", ad: "Webhook'lar" },
    { k: "guvenlik", ad: "Güvenlik" },
    { k: "sayfalar", ad: "Model Sayfaları", website: true },
    { k: "filtreler", ad: "Filtre Kuralları" },
];

/**
 * Atlas Studio istemci eylemi (Enterprise Studio eşleniği): ana ekran (uygulamalar, yeni uygulama, dışa/içe aktar),
 * üst çubuk (menü düzenle, yeni model, sekmeler, kapat) ve sekmelere göre görünüm / rapor düzenleyicileri.
 */
export class AtlasStudio extends Component {
    static template = "atlas_studio.Studio";
    static components = { AtlasStudioEditor };
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.tuvalRef = signal.ref();
        const params = this.props.action.params || {};
        const onceki = this.props.state || {};
        this.state = proxy({
            ekran: "ana",
            baglam: null,
            sekme: onceki.sekme || "gorunumler",
            editorTur: onceki.editorTur || null,
            editorAnahtar: 0,
            uygulamalar: [],
            kaydedildi: false,
            diyalog: null,
            raporlar: [],
            rapor: null,
            onizleme: "",
            eylemAyar: null,
            menuAgaci: null,
            ozellikler: [],
            raporAlanlari: [],
            gecerliSimgeler: [],
        });
        this.donusEylemi = params.donus_action_id || false;
        useSetupAction({
            getLocalState: () => ({
                sekme: this.state.sekme,
                editorTur: this.state.editorTur,
                action_id: this.state.baglam?.eylem?.id,
                model: this.state.baglam?.model,
            }),
        });
        onWillStart(async () => {
            this.state.ozellikler = await this.orm.call("atlas.studio", "ozellik_listesi", []);
            const eylemId = onceki.action_id || params.action_id;
            const model = onceki.model || params.model;
            if (eylemId || model) {
                await this.ac(eylemId, model, onceki.editorTur || (GORSEL.includes(params.view_type) ? params.view_type : params.view_type || null));
            } else {
                await this.anaEkran();
            }
        });
        onMounted(() => document.body.classList.add("o_atlas_studio_acik"));
        onWillUnmount(() => document.body.classList.remove("o_atlas_studio_acik"));
    }

    // ------------------------------------------------------------------ gezinme
    async anaEkran() {
        this.state.ekran = "ana";
        this.state.baglam = null;
        this.state.editorTur = null;
        this.state.uygulamalar = await this.orm.call("atlas.studio", "uygulamalar", []);
    }

    async ac(eylemId, model, tur = null) {
        try {
            const baglam = await this.orm.call("atlas.studio", "baglam", [eylemId || false, model || false]);
            if (!baglam.model) {
                return this.anaEkran();
            }
            this.state.baglam = baglam;
            this.state.ekran = "uygulama";
            this.state.editorTur = tur;
            this.state.editorAnahtar++;
            this.donusEylemi = baglam.eylem.id;
            if (this.state.sekme === "raporlar") {
                await this.raporlariYukle();
            }
        } catch (hata) {
            this.hata(hata);
            await this.anaEkran();
        }
    }

    async uygulamaAc(u) {
        if (!u.eylem_id) {
            this.notification.add("Bu uygulamada düzenlenebilir bir pencere eylemi yok.", { type: "warning" });
            return;
        }
        this.state.sekme = "gorunumler";
        await this.ac(u.eylem_id, false, null);
    }

    hata(h) {
        this.notification.add(hataMetni(h), { type: "danger", title: "Studio" });
    }

    kaydedildi() {
        this.state.kaydedildi = true;
        clearTimeout(this._kayitZaman);
        this._kayitZaman = setTimeout(() => (this.state.kaydedildi = false), 2500);
    }

    async kapat() {
        document.body.classList.remove("o_atlas_studio_acik");
        const hedef = this.state.baglam?.eylem?.id || this.donusEylemi;
        if (hedef) {
            const tur = this.state.editorTur && this.state.editorTur !== "search" ? this.state.editorTur : undefined;
            return this.action.doAction(hedef, { clearBreadcrumbs: true, viewType: tur }).catch(() => this.action.doAction("menu"));
        }
        return this.action.doAction({ type: "ir.actions.client", tag: "reload" });
    }

    async sekmeSec(k) {
        const b = this.state.baglam;
        const ortak = { views: [[false, "list"], [false, "form"]], target: "current" };
        const ac = (eylem) => this.action.doAction({ type: "ir.actions.act_window", ...ortak, ...eylem });
        switch (k) {
            case "otomasyonlar":
                return ac({ name: `Otomasyonlar: ${b.model_adi}`, res_model: "base.automation", domain: [["model_id", "=", b.model_id]],
                            context: { default_model_id: b.model_id } });
            case "aksiyonlar":
                return ac({ name: `Sunucu Eylemleri: ${b.model_adi}`, res_model: "ir.actions.server", domain: [["model_id", "=", b.model_id]],
                            context: { default_model_id: b.model_id } });
            case "webhooklar":
                return ac({ name: `Webhook'lar: ${b.model_adi}`, res_model: "base.automation",
                            domain: [["model_id", "=", b.model_id], ["trigger", "=", "on_webhook"]],
                            context: { default_model_id: b.model_id, default_trigger: "on_webhook" } });
            case "guvenlik":
                return ac({ name: `Erişim Hakları: ${b.model_adi}`, res_model: "ir.access", domain: [["model_id", "=", b.model_id]],
                            context: { default_model_id: b.model_id } });
            case "sayfalar":
                return ac({ name: `Model Sayfaları: ${b.model_adi}`, res_model: "website.controller.page", domain: [["model", "=", b.model]],
                            context: { default_model: b.model } });
            case "filtreler":
                return ac({ name: `Filtreler: ${b.model_adi}`, res_model: "ir.filters", domain: [["model_id", "=", b.model]],
                            context: { default_model_id: b.model } });
        }
        this.state.sekme = k;
        this.state.rapor = null;
        if (k === "raporlar") {
            await this.raporlariYukle();
        }
        if (k === "gorunumler") {
            this.state.editorTur = null;
        }
    }

    get sekmeler() {
        return SEKMELER.filter((s) => !s.website || this.state.baglam?.website);
    }

    // ------------------------------------------------------------------ görünümler sekmesi
    gorunumKategorileri() {
        const adlar = { genel: "Genel", coklu: "Çoklu Kayıt", zaman: "Zaman Çizelgesi", rapor: "Raporlama" };
        const gruplar = {};
        for (const g of this.state.baglam.gorunum_turleri) {
            (gruplar[g.kategori] ||= []).push(g);
        }
        return Object.entries(gruplar).map(([k, liste]) => ({ k, ad: adlar[k] || k, liste }));
    }

    async gorunumIslem(g, islem, ev) {
        ev?.stopPropagation();
        try {
            this.state.baglam = await this.orm.call("atlas.studio", "gorunum_turu_ayarla", [this.state.baglam.eylem.id, g.tur, islem]);
            this.kaydedildi();
        } catch (h) {
            this.hata(h);
        }
    }

    async gorunumDuzenle(g) {
        if (!g.kullanilabilir) {
            return;
        }
        if (!g.aktif) {
            await this.gorunumIslem(g, "etkinlestir");
        }
        this.state.editorTur = g.tur;
        this.state.editorAnahtar++;
    }

    gorunumSimgesi(tur) {
        return { form: "edit_square", search: "search", activity: "schedule", list: "view_list", kanban: "table_view", atlas_harita: "location_on",
                 calendar: "calendar_today", atlas_gantt: "bar_chart", graph: "show_chart", pivot: "table_view", atlas_kohort: "pie_chart" }[tur] || "widgets";
    }

    eylemAyarAc() {
        const e = this.state.baglam.eylem;
        this.state.eylemAyar = { ad: e.ad, yardim: (e.yardim || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim(), gruplar: [...e.gruplar], arama: "", sonuc: [] };
    }

    async eylemGrupAra(ev) {
        const a = this.state.eylemAyar;
        a.arama = ev.target.value;
        a.sonuc = a.arama.length >= 2 ? await this.orm.call("atlas.studio", "grup_ara", [a.arama]) : [];
    }

    async eylemAyarKaydet() {
        const a = this.state.eylemAyar;
        try {
            await this.orm.call("atlas.studio", "eylem_kaydet", [this.state.baglam.eylem.id, {
                ad: a.ad, yardim: a.yardim ? `<p class="o_view_nocontent_smiling_face">${a.yardim.replace(/</g, "&lt;")}</p>` : "",
                gruplar: a.gruplar.map((g) => g[0]) }]);
            this.state.eylemAyar = null;
            this.state.baglam = await this.orm.call("atlas.studio", "baglam", [this.state.baglam.eylem.id, false]);
            this.kaydedildi();
        } catch (h) {
            this.hata(h);
        }
    }

    // ------------------------------------------------------------------ raporlar sekmesi
    async raporlariYukle() {
        this.state.raporlar = await this.orm.call("atlas.studio", "raporlar", [this.state.baglam.model]);
    }

    yeniRapor() {
        this.state.diyalog = { tur: "rapor", ad: `${this.state.baglam.model_adi}`, duzen: "dis" };
    }

    async raporOlustur() {
        const dl = this.state.diyalog;
        try {
            const sonuc = await this.orm.call("atlas.studio", "rapor_olustur", [this.state.baglam.model, dl.ad, dl.duzen]);
            this.state.diyalog = null;
            await this.raporlariYukle();
            await this.raporAc(sonuc.id);
            this.kaydedildi();
        } catch (h) {
            this.hata(h);
        }
    }

    async raporAc(id) {
        try {
            const r = await this.orm.call("atlas.studio", "rapor_getir", [id]);
            this.state.rapor = { ...r, metin: r.arch, alan: "" };
            this.state.raporAlanlari = await this.raporAlanlari();
            await this.raporOnizle();
        } catch (h) {
            this.hata(h);
        }
    }

    async raporOnizle() {
        this.state.onizleme = await this.orm.call("atlas.studio", "rapor_onizle", [this.state.rapor.id]);
    }

    async raporKaydet() {
        const r = this.state.rapor;
        try {
            const yeni = await this.orm.call("atlas.studio", "rapor_kaydet", [r.id], {
                arch: r.metin, ad: r.ad, yazdir_menusu: r.yazdir_menusu, dosya_adi: r.dosya_adi });
            this.state.rapor = { ...yeni, metin: yeni.arch, alan: "" };
            await this.raporOnizle();
            await this.raporlariYukle();
            this.kaydedildi();
        } catch (h) {
            this.hata(h);
        }
    }

    raporAlanEkle(ev) {
        const ad = ev.target.value;
        if (!ad) {
            return;
        }
        const ta = document.querySelector(".o_as_rapor_kod");
        const parca = `<span t-field="doc.${ad}"/>`;
        const r = this.state.rapor;
        if (ta) {
            const i = ta.selectionStart ?? r.metin.length;
            r.metin = r.metin.slice(0, i) + parca + r.metin.slice(i);
        } else {
            r.metin += parca;
        }
        ev.target.value = "";
    }

    raporSil() {
        this.state.diyalog = { tur: "onayla", metin: `"${this.state.rapor.ad}" raporu silinsin mi?`, eylem: async () => {
            await this.orm.call("atlas.studio", "rapor_sil", [this.state.rapor.id]);
            this.state.rapor = null;
            await this.raporlariYukle();
        } };
    }

    async raporAlanlari() {
        if (!this._raporAlanlari) {
            const alanlar = await this.orm.call(this.state.baglam.model, "fields_get", [], { attributes: ["string", "type"] });
            this._raporAlanlari = Object.entries(alanlar).map(([a, f]) => [a, f.string]).sort((x, y) => x[1].localeCompare(y[1], "tr"));
        }
        return this._raporAlanlari;
    }

    // ------------------------------------------------------------------ menü düzenleyici
    async menuDuzenle() {
        const kok = this.state.baglam.menu.kok_id;
        if (!kok) {
            this.notification.add("Bu ekran bir menüye bağlı değil.", { type: "warning" });
            return;
        }
        const agac = await this.orm.call("atlas.studio", "menu_agaci", [kok]);
        this.state.menuAgaci = { kok: agac, duz: this.duzlestir(agac.cocuklar, 0), yeni: { ad: "", tur: "yeni_model", model: "", modeller: [] } };
    }

    duzlestir(liste, derinlik) {
        return liste.flatMap((m) => [{ id: m.id, ad: m.ad, derinlik, eylem: m.eylem }, ...this.duzlestir(m.cocuklar, derinlik + 1)]);
    }

    agaclastir(duz) {
        const kok = [];
        const yigin = [{ derinlik: -1, cocuklar: kok }];
        for (const m of duz) {
            while (yigin.at(-1).derinlik >= m.derinlik) {
                yigin.pop();
            }
            const d = { id: m.id, ad: m.ad, cocuklar: [] };
            yigin.at(-1).cocuklar.push(d);
            yigin.push({ derinlik: m.derinlik, cocuklar: d.cocuklar });
        }
        return kok;
    }

    menuTasi(i, yon) {
        const duz = this.state.menuAgaci.duz;
        const j = i + yon;
        if (j < 0 || j >= duz.length) {
            return;
        }
        [duz[i], duz[j]] = [duz[j], duz[i]];
        this.menuDerinlikDuzelt();
    }

    menuGirinti(i, fark) {
        const duz = this.state.menuAgaci.duz;
        const ust = i > 0 ? duz[i - 1].derinlik + 1 : 0;
        duz[i].derinlik = Math.max(0, Math.min(ust, duz[i].derinlik + fark, 1));
        this.menuDerinlikDuzelt();
    }

    menuDerinlikDuzelt() {
        const duz = this.state.menuAgaci.duz;
        duz.forEach((m, i) => {
            m.derinlik = Math.min(m.derinlik, i > 0 ? duz[i - 1].derinlik + 1 : 0, 1);
        });
    }

    async menuKaydet() {
        try {
            await this.orm.call("atlas.studio", "menu_kaydet", [this.state.menuAgaci.kok.id, this.agaclastir(this.state.menuAgaci.duz)]);
            this.state.menuAgaci = null;
            this.kaydedildi();
            this.notification.add("Menü kaydedildi. Değişiklikler sayfa yenilenince menüde görünür.", { type: "success" });
        } catch (h) {
            this.hata(h);
        }
    }

    async menuSil(i) {
        const m = this.state.menuAgaci.duz[i];
        try {
            await this.orm.call("atlas.studio", "menu_sil", [m.id]);
            await this.menuDuzenle();
        } catch (h) {
            this.hata(h);
        }
    }

    async menuModelAra(ev) {
        this.state.menuAgaci.yeni.modeller = await this.orm.call("atlas.studio", "modeller", [ev.target.value]);
    }

    async menuEkle() {
        const y = this.state.menuAgaci.yeni;
        if (!y.ad) {
            return;
        }
        try {
            await this.orm.call("atlas.studio", "menu_olustur", [this.state.menuAgaci.kok.id, y.ad, y.tur, y.model || false, null]);
            await this.menuDuzenle();
            this.kaydedildi();
        } catch (h) {
            this.hata(h);
        }
    }

    // ------------------------------------------------------------------ yeni model / uygulama
    yeniModel() {
        this.state.diyalog = { tur: "model", ad: "", secili: Object.fromEntries(this.state.ozellikler.map((o) => [o.anahtar, o.varsayilan])) };
    }

    async modelOlustur() {
        const dl = this.state.diyalog;
        if (!dl.ad) {
            return;
        }
        try {
            const ozellikler = Object.entries(dl.secili).filter(([, v]) => v).map(([k]) => k);
            const sonuc = await this.orm.call("atlas.studio", "menu_olustur", [this.state.baglam.menu.kok_id, dl.ad, "yeni_model", false, ozellikler]);
            this.state.diyalog = null;
            const menu = await this.orm.read("ir.ui.menu", [sonuc.id], ["action"]);
            const eylemId = parseInt(String(menu[0].action).split(",")[1], 10);
            this.kaydedildi();
            await this.ac(eylemId, false, "form");
        } catch (h) {
            this.hata(h);
        }
    }

    yeniUygulama() {
        this.state.diyalog = {
            tur: "uygulama", adim: 1, ad: "", modelAd: "", arkaPlan: RENKLER[0], renk: "#FFFFFF", simge: "apps",
            secili: Object.fromEntries(this.state.ozellikler.map((o) => [o.anahtar, o.varsayilan])),
        };
        this.simgeleriHazirla();
    }

    simgeDuzenle(u, ev) {
        ev.stopPropagation();
        this.state.diyalog = { tur: "simge", menuId: u.id, ad: u.ad, arkaPlan: RENKLER[1], renk: "#FFFFFF", simge: "apps" };
        this.simgeleriHazirla();
    }

    async simgeleriHazirla() {
        try {
            await document.fonts.load('48px "Material Symbols Outlined"', "apps");
        } catch {
            // yazı tipi yüklenemezse liste olduğu gibi kalır
        }
        this.state.gecerliSimgeler = SIMGELER.filter((s) => simgeGecerli(s));
        this.simgeYenile();
    }

    get renkler() {
        return RENKLER;
    }

    simgeYenile() {
        const tuval = this.tuvalRef();
        const dl = this.state.diyalog;
        if (tuval && dl) {
            dl.png = simgeCiz(tuval, dl);
        }
    }

    simgeSec(alan, deger) {
        this.state.diyalog[alan] = deger;
        Promise.resolve().then(() => this.simgeYenile());
    }

    async uygulamaOlustur() {
        const dl = this.state.diyalog;
        if (dl.adim === 1) {
            if (!dl.ad) {
                return;
            }
            this.simgeYenile();
            dl.adim = 2;
            return;
        }
        try {
            const ozellikler = Object.entries(dl.secili).filter(([, v]) => v).map(([k]) => k);
            const sonuc = await this.orm.call("atlas.studio", "uygulama_olustur", [dl.ad, dl.png || false, dl.modelAd || dl.ad, ozellikler]);
            this.state.diyalog = null;
            this.kaydedildi();
            await this.ac(sonuc.action_id, false, "form");
        } catch (h) {
            this.hata(h);
        }
    }

    async simgeKaydet() {
        const dl = this.state.diyalog;
        this.simgeYenile();
        try {
            await this.orm.call("atlas.studio", "uygulama_simge", [dl.menuId, dl.png]);
            this.state.diyalog = null;
            await this.anaEkran();
            this.kaydedildi();
        } catch (h) {
            this.hata(h);
        }
    }

    uygulamaSimgeUrl(u) {
        if (u.simge_veri) {
            return `/web/image/ir.ui.menu/${u.id}/web_icon_data`;
        }
        if (u.simge && u.simge.includes(",")) {
            const [modul, yol] = u.simge.split(",");
            return `/${modul}/${yol}`;
        }
        return "/base/static/description/icon.png";
    }

    disaAktar() {
        window.location.href = "/atlas_studio/disa_aktar";
    }

    async iceAktar() {
        try {
            await this.action.doAction("base_import_module.action_view_base_module_import");
        } catch {
            this.notification.add("İçe aktarma için 'Modül İçe Aktar' (base_import_module) kurulu olmalı.", { type: "warning" });
        }
    }

    // ------------------------------------------------------------------ ortak diyalog
    async onaylaCalistir() {
        const eylem = this.state.diyalog.eylem;
        this.state.diyalog = null;
        try {
            await eylem();
        } catch (h) {
            this.hata(h);
        }
    }
}

registry.category("actions").add("atlas_studio.studio", AtlasStudio);
