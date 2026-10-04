import { Component, onWillDestroy, proxy, useListener } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { useService } from "@web/core/utils/hooks";
import { WebClient } from "@web/webclient/webclient";

const STORAGE_KEY = "atlas_menu";

function readStorage() {
    try {
        return JSON.parse(browser.localStorage.getItem(STORAGE_KEY) || "{}");
    } catch {
        return {};
    }
}

/**
 * Akordeon sol menü: uygulamalar (başlık) ▸ bölümler ▸ işlemler.
 * Veriyi Odoo menü servisinden okur; tıklanan işlem `menu.selectMenu` ile açılır.
 */
export class AtlasSidebar extends Component {
    static template = "atlas_menu.Sidebar";

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.ui = proxy(useService("ui"));
        const stored = readStorage();
        this.state = proxy({
            open: stored.open || {},
            collapsed: !!stored.collapsed,
            search: "",
            activeMenuId: null,
            appId: null,
        });
        this.syncApp();
        useListener(this.env.bus, "MENUS:APP-CHANGED", () => this.syncApp());
        useListener(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => this.syncActive());
        this.applyBodyClass();
        onWillDestroy(() => document.body.classList.remove("o_atlas_menu", "o_atlas_menu_collapsed"));
    }

    // ------------------------------------------------------------------
    // Durum
    // ------------------------------------------------------------------

    save() {
        try {
            browser.localStorage.setItem(STORAGE_KEY, JSON.stringify({ open: this.state.open, collapsed: this.state.collapsed }));
        } catch {
            // depolama kapalıysa yalnızca bu oturumda geçerli
        }
    }

    applyBodyClass() {
        document.body.classList.add("o_atlas_menu");
        document.body.classList.toggle("o_atlas_menu_collapsed", this.state.collapsed);
    }

    syncApp() {
        const app = this.menuService.getCurrentApp();
        this.state.appId = app ? app.id : null;
        if (app && this.state.open[app.id] === undefined) {
            this.state.open[app.id] = true;
        }
        this.syncActive();
    }

    syncActive() {
        const actionId = this.actionService.currentController?.action?.id;
        if (!actionId) {
            return;
        }
        // Uygulama başlığı da çoğu zaman aynı action'a bağlıdır; alt işlem (yaprak) tercih edilir
        const menus = this.menuService.getAll().filter((m) => m.actionID === actionId && m.id !== "root");
        const puan = (m) => (m.appID === this.state.appId ? 2 : 0) + (m.id !== m.appID ? 1 : 0);
        const menu = menus.sort((a, b) => puan(b) - puan(a))[0];
        if (menu) {
            this.state.activeMenuId = menu.id;
            this.openParents(menu);
            // Aktif kalem görünür alana kaysın (render sonrası)
            browser.requestAnimationFrame(() =>
                document.querySelector(".o_atlas_sidebar .o_atlas_active")?.scrollIntoView({ block: "nearest" })
            );
        }
    }

    openParents(menu) {
        // Aktif işlemin bulunduğu bölüm(ler) ve uygulama açık olsun
        const byId = (id) => this.menuService.getMenu(id);
        const parents = this.menuService.getAll().filter((m) => m.children?.includes(menu.id));
        for (const parent of parents) {
            if (parent.id !== "root" && !this.state.open[parent.id]) {
                this.state.open[parent.id] = true;
                if (parent.appID && parent.appID !== parent.id) {
                    this.openParents(byId(parent.id));
                }
            }
        }
    }

    // ------------------------------------------------------------------
    // Veri
    // ------------------------------------------------------------------

    get apps() {
        return this.menuService.getApps();
    }

    children(menu) {
        return this.menuService.getMenuAsTree(menu.id).childrenTree || [];
    }

    appIcon(app) {
        if (app.webIconData) {
            return { image: app.webIconData };
        }
        if (app.webIcon) {
            const [cls, color, bg] = app.webIcon.split(",");
            return { icon: cls, color, bg };
        }
        return { letter: (app.name || "?").charAt(0).toUpperCase() };
    }

    href(menu) {
        if (!menu.actionID) {
            return "#";
        }
        return `/odoo/${menu.actionPath || "action-" + menu.actionID}`;
    }

    isOpen(menu) {
        return !!this.state.open[menu.id];
    }

    isActiveBranch(menu) {
        if (!this.state.activeMenuId) {
            return false;
        }
        const stack = [menu];
        while (stack.length) {
            const m = stack.pop();
            if (m.id === this.state.activeMenuId) {
                return true;
            }
            stack.push(...(this.menuService.getMenuAsTree(m.id).childrenTree || []));
        }
        return false;
    }

    get searchResults() {
        const term = this.state.search.trim().toLocaleLowerCase("tr");
        if (!term) {
            return [];
        }
        const results = [];
        const walk = (menu, path) => {
            for (const child of this.children(menu)) {
                const childPath = [...path, child.name];
                if (child.actionID && child.name.toLocaleLowerCase("tr").includes(term)) {
                    results.push({ menu: child, path: path.join(" › ") });
                }
                walk(child, childPath);
            }
        };
        for (const app of this.apps) {
            if (app.actionID && app.name.toLocaleLowerCase("tr").includes(term) && !this.children(app).length) {
                results.push({ menu: app, path: "" });
            }
            walk(app, [app.name]);
        }
        return results.slice(0, 40);
    }

    // ------------------------------------------------------------------
    // Olaylar
    // ------------------------------------------------------------------

    toggle(menu) {
        this.state.open[menu.id] = !this.state.open[menu.id];
        this.save();
    }

    onAppClick(app) {
        if (this.state.collapsed) {
            this.state.collapsed = false;
            this.applyBodyClass();
            this.state.open[app.id] = true;
            this.save();
            return;
        }
        if (!this.children(app).length) {
            return this.open(app);
        }
        this.toggle(app);
    }

    async open(menu, ev) {
        if (ev && (ev.ctrlKey || ev.metaKey || ev.button === 1)) {
            return; // yeni sekmede açılsın (href)
        }
        ev?.preventDefault();
        this.state.activeMenuId = menu.id;
        await this.menuService.selectMenu(menu);
    }

    toggleCollapsed() {
        this.state.collapsed = !this.state.collapsed;
        this.state.search = "";
        this.applyBodyClass();
        this.save();
    }

    collapseAll() {
        this.state.open = {};
        this.save();
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
    }

    onSearchKeydown(ev) {
        if (ev.key === "Escape") {
            ev.target.value = "";
            this.state.search = "";
        } else if (ev.key === "Enter" && this.searchResults.length) {
            this.open(this.searchResults[0].menu);
            ev.target.value = "";
            this.state.search = "";
        }
    }
}

WebClient.components = { ...WebClient.components, AtlasSidebar };
