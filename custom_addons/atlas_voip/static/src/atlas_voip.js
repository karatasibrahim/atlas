import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { openPhoneLink } from "@web/core/phone/phone_call";

/** Ortak arama işlevi: santral API'si varsa santralden, yoksa bilgisayardaki softphone (tel:) ile. */
async function ara(env, { phoneNumber, resModel, resId }, fallback) {
    const orm = env.services.orm;
    const notification = env.services.notification;
    try {
        const sonuc = await orm.call("atlas.voip.cagri", "atlas_ara", [phoneNumber, resModel || false, resId || false]);
        if (sonuc.yontem === "tel") {
            return fallback ? fallback() : (openPhoneLink(phoneNumber), true);
        }
        notification.add(_t("Arama başlatıldı: önce dahili telefonunuz çalacak, açınca %s aranacak.", phoneNumber), {
            type: "success",
        });
        return true;
    } catch (hata) {
        notification.add(hata.data?.message || hata.message || String(hata), { type: "danger" });
        return false;
    }
}

registry.category("phone_call_handlers").add("atlas_voip", {
    execute: (env, params, { fallback }) => ara(env, params, fallback),
});

registry.category("actions").add("atlas_voip.ara", async (env, action) => {
    const p = action.params || {};
    await ara(env, { phoneNumber: p.numara, resModel: p.res_model, resId: p.res_id });
});

/** Gelen arama bildirimleri (santral olayı → bus → ekran). */
const atlasVoipService = {
    dependencies: ["bus_service", "notification", "action"],
    start(env, { bus_service, notification, action }) {
        bus_service.subscribe("atlas_voip/gelen", (yuk) => {
            const kim = yuk.partner_ad || yuk.numara;
            const buttons = [];
            if (yuk.partner_id) {
                buttons.push({
                    name: _t("Kişiyi Aç"),
                    primary: true,
                    onClick: () =>
                        action.doAction({ type: "ir.actions.act_window", res_model: "res.partner", res_id: yuk.partner_id, views: [[false, "form"]] }),
                });
            } else {
                buttons.push({
                    name: _t("Kişi Oluştur"),
                    primary: true,
                    onClick: () =>
                        action.doAction({
                            type: "ir.actions.act_window",
                            res_model: "res.partner",
                            views: [[false, "form"]],
                            context: { default_phone: yuk.numara },
                        }),
                });
            }
            buttons.push({
                name: _t("Görüşme Kaydı"),
                onClick: () =>
                    action.doAction({ type: "ir.actions.act_window", res_model: "atlas.voip.cagri", res_id: yuk.cagri_id, views: [[false, "form"]] }),
            });
            notification.add(yuk.sirket ? `${kim} · ${yuk.sirket}` : kim, {
                title: _t("Gelen arama: %s", yuk.numara),
                type: "info",
                sticky: true,
                buttons,
            });
        });
        bus_service.subscribe("atlas_voip/cevapsiz", (yuk) => {
            notification.add(_t("Cevapsız arama: %s", yuk.partner_ad || yuk.numara), { type: "warning" });
        });
        bus_service.start();
        return {};
    },
};

registry.category("services").add("atlas_voip", atlasVoipService);
