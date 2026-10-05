/** Atlas Studio istemci yardımcıları: arşiv ağacı, simge çizimi, sabitler. */

/**
 * Görünüm arşivini (XML metni) düz nesne ağacına çevirir. Her düğümün "yol"u, sunucudaki
 * atlas.studio._dugum() ile aynı biçimdedir: kökten itibaren öğe çocuklarının sıra numaraları.
 */
export function archAgaci(xmlMetni) {
    const belge = new DOMParser().parseFromString(xmlMetni, "text/xml");
    const harita = new Map();
    const donustur = (el, yol, ust) => {
        const d = {
            tag: el.tagName,
            attrs: Object.fromEntries([...el.attributes].map((a) => [a.name, a.value])),
            yol,
            anahtar: yol.length ? yol.join("-") : "kok",
            ust,
            text: [...el.childNodes]
                .filter((n) => n.nodeType === 3)
                .map((n) => n.nodeValue)
                .join(" ")
                .replace(/\s+/g, " ")
                .trim(),
        };
        d.children = [...el.children].map((c, i) => donustur(c, [...yol, i], d));
        harita.set(d.anahtar, d);
        return d;
    };
    const kok = donustur(belge.documentElement, [], null);
    return { kok, harita };
}

/** invisible="1" / "True" gibi sabit ifadeler */
export function sabitDogru(deger) {
    return ["1", "True", "true"].includes((deger || "").trim());
}

export function sabitMi(deger) {
    return ["", "0", "1", "True", "true", "False", "false"].includes((deger || "").trim());
}

export function alanSimgesi(tur) {
    return (
        {
            char: "text_fields",
            text: "article",
            integer: "add",
            float: "add_2",
            html: "description",
            monetary: "payments",
            date: "calendar_today",
            datetime: "schedule",
            boolean: "check_box",
            selection: "arrow_drop_down",
            binary: "attach_file",
            lines: "list_alt",
            one2many: "view_list",
            many2one: "link",
            many2many: "account_tree",
            image: "image",
            tags: "sell",
            priority: "star",
            signature: "edit",
            related: "share",
            reference: "link",
            properties: "widgets",
            json: "database",
        }[tur] || "text_fields"
    );
}

/** Uygulama simgesi tasarımcısında sunulan simgeler (geçersiz bağlar çizimde elenir) */
export const SIMGELER = [
    "apps", "shopping_cart", "receipt_long", "payments", "factory", "account_tree", "bar_chart", "pie_chart",
    "show_chart", "calendar_today", "schedule", "person", "group", "family_history", "business", "book",
    "description", "article", "folder", "database", "settings", "tune", "widgets", "star", "lightbulb",
    "location_on", "public", "mail", "call", "photo_camera", "videocam", "print", "qr_code", "sell",
    "verified", "lock", "history", "checklist", "assignment", "bug_report", "near_me", "share", "image",
    "local_shipping", "inventory_2", "event", "groups", "build", "school", "favorite", "home", "work",
    "pets", "restaurant", "flight", "savings", "support_agent", "engineering", "medical_services",
    "directions_car", "storefront", "bolt", "eco", "science", "palette", "campaign", "handshake",
    "account_balance", "rocket_launch", "psychology", "construction", "agriculture", "local_hospital",
];

export const RENKLER = [
    "#714B67", "#017E84", "#E46F78", "#F4A261", "#2A9D8F", "#264653", "#3C6E71", "#8E44AD",
    "#1F6FEB", "#C0392B", "#16A085", "#D35400", "#2C3E50", "#7F8C8D", "#F1C40F", "#FFFFFF",
];

const SIMGE_YAZI = "\"Material Symbols Outlined\"";

/** Bağ (ligature) yazı tipinde gerçekten bir simgeye dönüşüyor mu? (tek glif genişliği ve boş olmayan çizim) */
export function simgeGecerli(ad, boyut = 32) {
    const tuval = document.createElement("canvas");
    tuval.width = tuval.height = boyut * 2;
    const c = tuval.getContext("2d");
    c.font = `${boyut}px ${SIMGE_YAZI}`;
    if (c.measureText(ad).width > boyut * 1.6) {
        return false;
    }
    c.textBaseline = "middle";
    c.fillText(ad, boyut / 2, boyut);
    const veri = c.getImageData(0, 0, tuval.width, tuval.height).data;
    let dolu = 0;
    for (let i = 3; i < veri.length; i += 4) {
        if (veri[i] > 100) {
            dolu++;
        }
    }
    return dolu > boyut;
}

/** Uygulama simgesini PNG (base64, ön eksiz) olarak çizer */
export function simgeCiz(tuval, { arkaPlan, renk, simge }) {
    const boyut = tuval.width;
    const c = tuval.getContext("2d");
    c.clearRect(0, 0, boyut, boyut);
    const r = boyut * 0.18;
    c.beginPath();
    c.moveTo(r, 0);
    c.arcTo(boyut, 0, boyut, boyut, r);
    c.arcTo(boyut, boyut, 0, boyut, r);
    c.arcTo(0, boyut, 0, 0, r);
    c.arcTo(0, 0, boyut, 0, r);
    c.closePath();
    const egim = c.createLinearGradient(0, 0, 0, boyut);
    egim.addColorStop(0, arkaPlan);
    egim.addColorStop(1, golgele(arkaPlan, -0.18));
    c.fillStyle = egim;
    c.fill();
    c.fillStyle = renk;
    c.font = `${Math.round(boyut * 0.56)}px ${SIMGE_YAZI}`;
    c.textAlign = "center";
    c.textBaseline = "middle";
    c.fillText(simge, boyut / 2, boyut / 2 + boyut * 0.02);
    return tuval.toDataURL("image/png").split(",")[1];
}

function golgele(hex, oran) {
    const n = parseInt(hex.slice(1), 16);
    const kanal = (k) => Math.max(0, Math.min(255, Math.round(k + k * oran)));
    const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(kanal);
    return `rgb(${r}, ${g}, ${b})`;
}

export function hataMetni(hata) {
    return hata?.data?.message || hata?.message || String(hata);
}
