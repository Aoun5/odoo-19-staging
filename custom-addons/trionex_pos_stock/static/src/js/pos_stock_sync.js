/** @odoo-module **/

import { registry } from "@web/core/registry";

// Live POS stock sync.
//
// Subscribes this till to its own bus channel. When the server pushes a
// POS_STOCK_UPDATE (because on-hand stock changed somewhere), we patch the
// in-memory product records so the on-hand figure on order lines / product
// info re-renders reactively. No "Reload Data" / full refetch involved.
export const PosStockSyncService = {
    dependencies: ["bus_service", "pos"],

    start(env, { bus_service, pos }) {
        // Nothing to sync if this till does not display stock.
        if (!pos.config.pos_display_stock) {
            console.warn("[trionex_pos_stock] display stock OFF -> live sync disabled");
            return;
        }

        // No stock location on this till => the backend never pushes to our
        // channel (it only notifies tills that have a stock location), so the
        // figure shown is the GLOBAL on-hand at load time and can't live-update.
        if (!pos.config.stock_location_id) {
            console.warn(
                "[trionex_pos_stock] till '%s' has NO Stock Location set -> " +
                    "live qty sync is DISABLED. Set a Stock Location on this POS.",
                pos.config.name
            );
            return;
        }

        const channel = `pos_stock_update_${pos.config.id}`;
        bus_service.addChannel(channel);

        bus_service.subscribe("POS_STOCK_UPDATE", (payload) => {
            if (!payload?.data?.length) {
                return;
            }
            const products = pos.models["product.product"];
            for (const item of payload.data) {
                const product = products.get(item.product_id);
                if (!product) {
                    continue;
                }
                // Go through .update() explicitly: guaranteed reactive write
                // that notifies OWL to re-render the orderline / product card.
                product.update({ qty_available: item.qty_available });
            }
        });
    },
};

registry.category("services").add("pos_stock_sync_service", PosStockSyncService);
