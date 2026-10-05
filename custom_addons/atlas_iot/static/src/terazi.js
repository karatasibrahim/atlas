import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FloatField, floatField, floatFieldProps } from "@web/views/fields/float/float_field";

/**
 * Seri port (USB/RS232) teraziden kararlı ağırlık okur. Web Serial: Chrome/Edge, HTTPS veya localhost.
 * @returns {Promise<number>}
 */
export async function teraziOku({ baud = 9600, desen, kararlilik = 3, istekKomutu = "", zamanAsimi = 15000 }) {
    if (!("serial" in navigator)) {
        throw new Error(_t("Tarayıcınız teraziye bağlanamıyor. Chrome veya Edge kullanın ve sistemi HTTPS üzerinden açın."));
    }
    let [port] = await navigator.serial.getPorts();
    if (!port) {
        port = await navigator.serial.requestPort();
    }
    await port.open({ baudRate: baud || 9600 });
    const kod = new TextDecoderStream();
    const kapandi = port.readable.pipeTo(kod.writable).catch(() => {});
    const okuyucu = kod.readable.getReader();
    let yazici = null;
    let istekZamanlayici = null;
    if (istekKomutu) {
        yazici = port.writable.getWriter();
        const gonder = () => yazici.write(new TextEncoder().encode(`${istekKomutu}\r\n`)).catch(() => {});
        gonder();
        istekZamanlayici = setInterval(gonder, 500);
    }
    const ifade = new RegExp(desen || "([-+]?\\d+[.,]?\\d*)\\s*(kg|g)?", "i");
    let tampon = "";
    let son = null;
    let ayni = 0;
    const bitis = Date.now() + zamanAsimi;
    try {
        while (Date.now() < bitis) {
            const kalan = bitis - Date.now();
            const { value, done } = await Promise.race([
                okuyucu.read(),
                new Promise((cozum) => setTimeout(() => cozum({ value: "", done: false }), Math.min(kalan, 1000))),
            ]);
            if (done) {
                break;
            }
            tampon += value || "";
            const satirlar = tampon.split(/\r\n|\n|\r/);
            tampon = satirlar.pop();
            for (const satir of satirlar) {
                const m = ifade.exec(satir);
                if (!m) {
                    continue;
                }
                let deger = parseFloat(m[1].replace(",", "."));
                if (m[2] && m[2].toLowerCase() === "g") {
                    deger = deger / 1000;
                }
                if (son !== null && Math.abs(deger - son) < 1e-9) {
                    ayni++;
                } else {
                    son = deger;
                    ayni = 1;
                }
                if (ayni >= (kararlilik || 1)) {
                    return deger;
                }
            }
        }
        throw new Error(_t("Teraziden kararlı ağırlık okunamadı. Kefeyi sabitleyip tekrar deneyin."));
    } finally {
        clearInterval(istekZamanlayici);
        yazici?.releaseLock();
        await okuyucu.cancel().catch(() => {});
        await kapandi;
        await port.close().catch(() => {});
    }
}

export class AtlasTeraziField extends Component {
    static template = "atlas_iot.TeraziField";
    static components = { FloatField };
    props = useProps({ ...floatFieldProps, cihazAlani: t.string().optional() });

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ okuyor: false });
    }

    get floatProps() {
        const { cihazAlani, ...digerleri } = this.props;
        return digerleri;
    }

    async tart() {
        const kayit = this.props.record;
        const cihazDegeri = this.props.cihazAlani ? kayit.data[this.props.cihazAlani] : null;
        const cihazId = cihazDegeri?.id || (Array.isArray(cihazDegeri) ? cihazDegeri[0] : cihazDegeri);
        let ayar = {};
        if (cihazId) {
            const [c] = await this.orm.read("atlas.iot.cihaz", [cihazId], ["baud", "deger_deseni", "kararlilik", "istek_komutu"]);
            ayar = { baud: c.baud, desen: c.deger_deseni, kararlilik: c.kararlilik, istekKomutu: c.istek_komutu || "" };
        }
        this.state.okuyor = true;
        try {
            const deger = await teraziOku(ayar);
            await kayit.update({ [this.props.name]: deger });
            this.notification.add(_t("Tartıldı: %s", deger), { type: "success" });
        } catch (hata) {
            if (hata.name !== "NotFoundError") {
                this.notification.add(hata.message || String(hata), { type: "danger" });
            }
        } finally {
            this.state.okuyor = false;
        }
    }
}

registry.category("fields").add("atlas_terazi", {
    ...floatField,
    component: AtlasTeraziField,
    extractProps: (fieldInfo, dynamicInfo) => ({
        ...floatField.extractProps(fieldInfo, dynamicInfo),
        cihazAlani: fieldInfo.options.cihaz,
    }),
});
