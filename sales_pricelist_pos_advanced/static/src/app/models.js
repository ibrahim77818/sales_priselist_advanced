/** @odoo-module */

import { ProductProduct } from "@point_of_sale/app/models/product_product";
import { patch } from "@web/core/utils/patch";
import { roundPrecision } from "@web/core/utils/numbers";

/**
 * Port of product.pricelist.item._asp_apply_formula (Python): standard Odoo 18
 * formula extended with the percentage extra fee.
 * Order: discount (or markup on cost) -> rounding -> extra fees -> min/max margins.
 */
export function aspApplyFormula(rule, basePrice) {
    const priceLimit = basePrice;
    // Odoo 18 shows cost-based rules as a markup, stored as price_discount = -markup.
    let price = basePrice - basePrice * (rule.price_discount / 100);
    if (rule.price_round) {
        price = roundPrecision(price, rule.price_round);
    }
    const discountedPrice = price;
    if (rule.price_surcharge) {
        price += rule.price_surcharge;
    }
    if (rule.price_surcharge_percent) {
        const feeBasis = rule.price_surcharge_percent_base === "discounted" ? discountedPrice : basePrice;
        price += (feeBasis * rule.price_surcharge_percent) / 100;
    }
    if (rule.price_min_margin) {
        price = Math.max(price, priceLimit + rule.price_min_margin);
    }
    if (rule.price_max_margin) {
        price = Math.min(price, priceLimit + rule.price_max_margin);
    }
    return price;
}

patch(ProductProduct.prototype, {
    get_price(
        pricelist,
        quantity,
        price_extra = 0,
        recurring = false,
        list_price = false,
        original_line = false,
        related_lines = []
    ) {
        // Same quantity as the standard method for lot-tracked lines (all the
        // lines of the product), computed without touching `related_lines`.
        let ruleQty = quantity;
        if (original_line && original_line.isLotTracked()) {
            ruleQty = original_line.order_id.lines
                .filter((line) => line.product_id.id === this.id)
                .reduce((sum, line) => sum + line.get_quantity(), 0);
        }
        const rule = this.getPricelistRule(pricelist, ruleQty);
        if (!rule || rule.compute_price !== "formula" || !rule.price_surcharge_percent) {
            return super.get_price(...arguments);
        }
        // Base price, exactly as in ProductProduct.get_price (Odoo 18)
        let price = (list_price || this.lst_price) + (price_extra || 0);
        if (rule.base === "pricelist") {
            if (rule.base_pricelist_id) {
                price = this.get_price(rule.base_pricelist_id, ruleQty, price_extra, true, list_price);
            }
        } else if (rule.base === "standard_price") {
            price = this.standard_price;
        }
        return aspApplyFormula(rule, price);
    },
});
