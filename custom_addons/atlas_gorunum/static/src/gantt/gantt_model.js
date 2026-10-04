import { _t } from "@web/core/l10n/translation";
import {
    deserializeDate,
    deserializeDateTime,
    serializeDate,
    serializeDateTime,
} from "@web/core/l10n/dates";
import { exprToBoolean } from "@web/core/utils/strings";
import { KeepLast } from "@web/core/utils/concurrency";
import { Model } from "@web/model/model";

const { DateTime } = luxon;

export const OLCEKLER = {
    gun: { ad: _t("Gün"), birim: "day", sutun: "hour", adim: { minutes: 15 } },
    hafta: { ad: _t("Hafta"), birim: "week", sutun: "day", adim: { hours: 1 } },
    ay: { ad: _t("Ay"), birim: "month", sutun: "day", adim: { days: 1 } },
    yil: { ad: _t("Yıl"), birim: "year", sutun: "month", adim: { days: 1 } },
};

const GRUPLANABILIR = ["many2one", "many2many", "selection", "char", "boolean", "integer"];

export class AtlasGanttArchParser {
    parse(xmlDoc, models, modelName) {
        const fields = models[modelName].fields;
        const a = (ad) => xmlDoc.getAttribute(ad);
        const ekAlanlar = [...xmlDoc.querySelectorAll("field")].map((n) => n.getAttribute("name"));
        const info = {
            dateStart: a("date_start"),
            dateStop: a("date_stop"),
            defaultGroupBy: a("default_group_by"),
            color: a("color"),
            progress: a("progress"),
            label: a("label") || "display_name",
            defaultScale: OLCEKLER[a("default_scale")] ? a("default_scale") : "hafta",
            canCreate: exprToBoolean(a("create"), true),
            canEdit: exprToBoolean(a("edit"), true),
            ekAlanlar,
        };
        info.fieldNames = [
            ...new Set(
                ["display_name", info.dateStart, info.dateStop, info.defaultGroupBy, info.color, info.progress, info.label, ...ekAlanlar].filter(
                    (f) => f && fields[f]
                )
            ),
        ];
        return info;
    }
}

function m2oId(deger) {
    if (Array.isArray(deger)) {
        return deger[0];
    }
    return deger && typeof deger === "object" ? deger.id : deger;
}

function m2oAd(deger) {
    if (Array.isArray(deger)) {
        return deger[1];
    }
    return deger && typeof deger === "object" ? deger.display_name : deger;
}

export class AtlasGanttModel extends Model {
    setup(params) {
        this.resModel = params.resModel;
        this.fields = params.fields;
        this.arch = params.archInfo;
        this.olcek = params.state?.olcek || this.arch.defaultScale;
        this.odak = params.state?.odak ? DateTime.fromISO(params.state.odak) : DateTime.local();
        this.satirlar = [];
        this.kayitSayisi = 0;
        this.keepLast = new KeepLast();
        this.searchParams = { domain: [], context: {}, groupBy: [] };
    }

    exportState() {
        return { olcek: this.olcek, odak: this.odak.toISO() };
    }

    // ------------------------------------------------------------------
    // Tarih yardımcıları
    // ------------------------------------------------------------------

    alanTuru(alan) {
        return this.fields[alan]?.type;
    }

    tarihOku(alan, deger, bitisMi) {
        if (!deger) {
            return null;
        }
        if (this.alanTuru(alan) === "date") {
            const gun = deserializeDate(deger);
            return bitisMi ? gun.plus({ days: 1 }) : gun; // tarih alanı bitişi gün sonu dahil
        }
        return deserializeDateTime(deger);
    }

    tarihYaz(alan, dt, bitisMi) {
        if (this.alanTuru(alan) === "date") {
            return serializeDate(bitisMi ? dt.minus({ days: 1 }) : dt);
        }
        return serializeDateTime(dt);
    }

    get aralik() {
        const birim = OLCEKLER[this.olcek].birim;
        const bas = this.odak.startOf(birim);
        return { bas, bit: bas.plus({ [birim + "s"]: 1 }) };
    }

    get sutunlar() {
        const { bas, bit } = this.aralik;
        const sutunBirim = OLCEKLER[this.olcek].sutun;
        const sonuc = [];
        let t = bas;
        while (t < bit) {
            const sonraki = t.plus({ [sutunBirim + "s"]: 1 });
            let etiket;
            if (sutunBirim === "hour") {
                etiket = t.toFormat("HH");
            } else if (sutunBirim === "day") {
                etiket = this.olcek === "hafta" ? t.toFormat("ccc d") : t.toFormat("d");
            } else {
                etiket = t.toFormat("LLL");
            }
            sonuc.push({
                anahtar: t.toISO(),
                bas: t,
                bit: sonraki,
                etiket,
                haftaSonu: sutunBirim === "day" && t.weekday >= 6,
                bugun: sutunBirim !== "hour" && t.hasSame(DateTime.local(), sutunBirim),
            });
            t = sonraki;
        }
        return sonuc;
    }

    get baslik() {
        const { bas, bit } = this.aralik;
        switch (this.olcek) {
            case "gun":
                return bas.toFormat("d MMMM yyyy, cccc");
            case "hafta":
                return `${bas.toFormat("d MMM")} – ${bit.minus({ days: 1 }).toFormat("d MMM yyyy")}`;
            case "ay":
                return bas.toFormat("MMMM yyyy");
            default:
                return bas.toFormat("yyyy");
        }
    }

    get grupAlani() {
        const arama = (this.searchParams.groupBy || [])[0];
        const alan = arama ? arama.split(":")[0] : this.arch.defaultGroupBy;
        return alan && GRUPLANABILIR.includes(this.alanTuru(alan)) ? alan : null;
    }

    // ------------------------------------------------------------------
    // Yükleme
    // ------------------------------------------------------------------

    async load(searchParams) {
        if (searchParams) {
            this.searchParams = searchParams;
        }
        const { bas, bit } = this.aralik;
        const { dateStart, dateStop } = this.arch;
        const domain = [
            ...(this.searchParams.domain || []),
            [dateStart, "<", this.tarihYaz(dateStart, bit)],
            "|",
            [dateStop, "=", false],
            [dateStop, this.alanTuru(dateStop) === "date" ? ">=" : ">", this.alanTuru(dateStop) === "date" ? serializeDate(bas) : serializeDateTime(bas)],
        ];
        const alanlar = [...this.arch.fieldNames];
        const grup = this.grupAlani;
        if (grup && !alanlar.includes(grup)) {
            alanlar.push(grup);
        }
        const kayitlar = await this.keepLast.add(
            this.orm.searchRead(this.resModel, domain, alanlar, {
                context: this.searchParams.context,
                order: `${dateStart} asc, id asc`,
                limit: 2000,
            })
        );
        await this._satirlariKur(kayitlar, grup);
        this.kayitSayisi = kayitlar.length;
        this.notify();
    }

    async _satirlariKur(kayitlar, grup) {
        const { dateStart, dateStop, color, progress, label } = this.arch;
        const satirlar = new Map();
        const satirAl = (anahtar, ad, deger) => {
            if (!satirlar.has(anahtar)) {
                satirlar.set(anahtar, { anahtar, ad, deger, cubuklar: [] });
            }
            return satirlar.get(anahtar);
        };
        const grupTuru = grup && this.alanTuru(grup);
        let m2mAdlari = {};
        if (grupTuru === "many2many") {
            const idler = [...new Set(kayitlar.flatMap((k) => k[grup] || []))];
            if (idler.length) {
                const okunan = await this.orm.read(this.fields[grup].relation, idler, ["display_name"]);
                m2mAdlari = Object.fromEntries(okunan.map((r) => [r.id, r.display_name]));
            }
        }
        const secimler = grupTuru === "selection" ? Object.fromEntries(this.fields[grup].selection) : {};
        const bos = _t("Atanmamış");
        for (const kayit of kayitlar) {
            let bas = this.tarihOku(dateStart, kayit[dateStart], false);
            if (!bas) {
                continue;
            }
            let bit = this.tarihOku(dateStop, kayit[dateStop], true);
            if (!bit || bit <= bas) {
                bit = bas.plus(this.alanTuru(dateStart) === "date" ? { days: 1 } : { hours: 1 });
            }
            const cubuk = {
                id: kayit.id,
                ad: m2oAd(kayit[label]) || kayit.display_name,
                bas,
                bit,
                renk: this._renk(color ? kayit[color] : null, color),
                ilerleme: progress ? Math.max(0, Math.min(100, kayit[progress] || 0)) : null,
                kayit,
            };
            if (!grup) {
                satirAl("hepsi", _t("Tümü"), false).cubuklar.push(cubuk);
            } else if (grupTuru === "many2many") {
                const idler = kayit[grup] || [];
                if (!idler.length) {
                    satirAl("bos", bos, false).cubuklar.push(cubuk);
                }
                for (const id of idler) {
                    // her satırın kendi şerit bilgisi olsun diye kopya
                    satirAl(`m2m_${id}`, m2mAdlari[id] || String(id), id).cubuklar.push({ ...cubuk });
                }
            } else {
                const deger = kayit[grup];
                const id = grupTuru === "many2one" ? m2oId(deger) : deger;
                let ad = grupTuru === "many2one" ? m2oAd(deger) : grupTuru === "selection" ? secimler[deger] : deger;
                if (grupTuru === "boolean") {
                    ad = deger ? _t("Evet") : _t("Hayır");
                }
                satirAl(id === false || id === null || id === undefined ? "bos" : `d_${id}`, ad || bos, id ?? false).cubuklar.push(cubuk);
            }
        }
        const sirali = [...satirlar.values()].sort((a, b) => {
            if (a.anahtar === "bos") {
                return 1;
            }
            if (b.anahtar === "bos") {
                return -1;
            }
            return String(a.ad).localeCompare(String(b.ad), "tr");
        });
        for (const satir of sirali) {
            this._seritlereYerlestir(satir);
        }
        this.satirlar = sirali;
    }

    _seritlereYerlestir(satir) {
        // Çakışan çubuklar alt alta şeritlere dizilir
        const seritSonlari = [];
        for (const cubuk of satir.cubuklar.sort((a, b) => a.bas - b.bas)) {
            let serit = seritSonlari.findIndex((son) => son <= cubuk.bas);
            if (serit === -1) {
                serit = seritSonlari.length;
                seritSonlari.push(cubuk.bit);
            } else {
                seritSonlari[serit] = cubuk.bit;
            }
            cubuk.serit = serit;
        }
        satir.seritSayisi = Math.max(1, seritSonlari.length);
    }

    _renk(deger, alan) {
        if (deger === null || deger === undefined || deger === false) {
            return 0;
        }
        const tur = this.alanTuru(alan);
        if (tur === "integer") {
            return Math.abs(deger) % 12;
        }
        if (tur === "many2one") {
            return (m2oId(deger) % 11) + 1;
        }
        if (tur === "selection") {
            const sira = this.fields[alan].selection.findIndex(([k]) => k === deger);
            return (sira % 11) + 1;
        }
        let h = 0;
        for (const c of String(deger)) {
            h = (h * 31 + c.charCodeAt(0)) | 0;
        }
        return (Math.abs(h) % 11) + 1;
    }

    // ------------------------------------------------------------------
    // Gezinme ve düzenleme
    // ------------------------------------------------------------------

    async olcekSec(olcek) {
        this.olcek = olcek;
        await this.load();
    }

    async kaydir(yon) {
        const birim = OLCEKLER[this.olcek].birim;
        this.odak = yon === 0 ? DateTime.local() : this.odak.plus({ [birim + "s"]: yon });
        await this.load();
    }

    yuvarla(dt) {
        const adim = this.alanTuru(this.arch.dateStart) === "date" ? { days: 1 } : OLCEKLER[this.olcek].adim;
        const ms = luxon.Duration.fromObject(adim).toMillis();
        const yerel = dt.toMillis() + dt.offset * 60000;
        return DateTime.fromMillis(Math.round(yerel / ms) * ms - dt.offset * 60000);
    }

    async cubukGuncelle(cubuk, yeniBas, yeniBit, hedefSatir) {
        const { dateStart, dateStop } = this.arch;
        const degerler = {};
        if (+yeniBas !== +cubuk.bas) {
            degerler[dateStart] = this.tarihYaz(dateStart, yeniBas, false);
        }
        if (+yeniBit !== +cubuk.bit) {
            degerler[dateStop] = this.tarihYaz(dateStop, yeniBit, true);
        }
        const grup = this.grupAlani;
        if (hedefSatir && grup && this.alanTuru(grup) !== "many2many" && hedefSatir.deger !== undefined) {
            const mevcut = this.alanTuru(grup) === "many2one" ? m2oId(cubuk.kayit[grup]) : cubuk.kayit[grup];
            if ((hedefSatir.deger ?? false) !== (mevcut ?? false)) {
                degerler[grup] = hedefSatir.deger;
            }
        }
        if (!Object.keys(degerler).length) {
            return false;
        }
        try {
            await this.orm.write(this.resModel, [cubuk.id], degerler, { context: this.searchParams.context });
        } finally {
            await this.load();
        }
        return true;
    }

    yeniKayitBaglami(satir, sutun) {
        const { dateStart, dateStop } = this.arch;
        const baglam = {
            [`default_${dateStart}`]: this.tarihYaz(dateStart, sutun.bas, false),
            [`default_${dateStop}`]: this.tarihYaz(dateStop, sutun.bit, true),
        };
        const grup = this.grupAlani;
        if (grup && satir && satir.deger !== false && satir.deger !== undefined) {
            baglam[`default_${grup}`] = this.alanTuru(grup) === "many2many" ? [satir.deger] : satir.deger;
        }
        return baglam;
    }
}
