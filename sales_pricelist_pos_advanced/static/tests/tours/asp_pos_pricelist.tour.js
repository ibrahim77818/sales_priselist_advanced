/* global posmodel */

import { registry } from "@web/core/registry";
import * as Chrome from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";

// [product name, pricelist name, quantity, expected price] -- expected values
// are computed by the backend engine in test_pos_ui.py (same scenarios).
const CASES = [
    ["ASP POS Fee Product", "ASP POS Fee on base", 1, 95.0],
    ["ASP POS Fee Product", "ASP POS Fee on discounted", 1, 94.5],
    ["ASP POS Fee Product", "ASP POS Fee rounded", 1, 104.5],
    ["ASP POS Fee Product", "ASP POS Fee on cost", 1, 67.0],
    ["ASP POS Fee Product", "ASP POS Fee markup on cost", 1, 70.0],
    ["ASP POS Fee Product", "ASP POS Fee capped", 1, 120.0],
    ["ASP POS Fee Product", "ASP POS Fee chained", 1, 99.75],
    ["ASP POS Fee Product", "ASP POS Fee min qty", 1, 100.0],
    ["ASP POS Fee Product", "ASP POS Fee min qty", 10, 110.0],
    ["ASP POS Fee Product", "ASP POS No fee", 1, 90.0],
    // packaging rule (Box of 5 = 450.00) is kept for quotations, never applied per unit
    ["ASP POS Fee Product", "ASP POS Packaging only", 5, 100.0],
];

registry.category("web_tour.tours").add("asp_pos_percent_fee_tour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            {
                content: "Check the browser prices against the backend engine",
                trigger: "body:not(:has(.pos-loader))",
                run: function () {
                    const models = posmodel.data.models;
                    const dp = models["decimal.precision"].find((d) => d.name === "Product Price");
                    const errors = [];
                    for (const [productName, pricelistName, qty, expected] of CASES) {
                        const product = models["product.template"]
                            .getAll()
                            .find((p) => p.display_name === productName);
                        const pricelist = models["product.pricelist"].find((pl) => pl.name === pricelistName);
                        if (!product || !pricelist) {
                            errors.push(`missing data: ${productName} / ${pricelistName}`);
                            continue;
                        }
                        const price = dp.round(
                            product.getPrice(pricelist, qty, 0, false, product.product_variant_ids[0])
                        );
                        if (Math.abs(price - expected) > 0.001) {
                            errors.push(`${pricelistName} x${qty}: ${price} != ${expected}`);
                        }
                    }
                    if (errors.length) {
                        throw new Error("ASP POS price mismatch: " + errors.join(" | "));
                    }
                },
            },
        ].flat(),
});
