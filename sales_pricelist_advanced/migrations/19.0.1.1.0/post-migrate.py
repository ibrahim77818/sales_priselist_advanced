# -*- coding: utf-8 -*-
"""Odoo 18 -> 19: packaging rules become unit rules.

Odoo 19 removed ``product.packaging``: packagings are units of measure now
(e.g. "Carton of 24" = 24 Units, listed in the product's Packagings). Rules of
this module that targeted a packaging (column ``packaging_id``) are moved to
the matching unit: same name and same quantity, preferably one of the
product's packagings. Rules that cannot be matched are archived... no:
pricelist rules cannot be archived, so they are left untouched and logged so
the administrator can set their Unit / Packaging by hand.

This script only runs when the old column and the old packaging table are
still in the database (they depend on how the database was upgraded).
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _column_exists(cr, table, column):
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
               (table, column))
    return bool(cr.fetchone())


def _table_exists(cr, table):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not _column_exists(cr, 'product_pricelist_item', 'packaging_id'):
        return
    if not _table_exists(cr, 'product_packaging'):
        cr.execute("SELECT count(*) FROM product_pricelist_item WHERE packaging_id IS NOT NULL AND uom_id IS NULL")
        count = cr.fetchone()[0]
        if count:
            _logger.warning(
                "sales_pricelist_advanced: %s pricelist rule(s) targeted a product packaging, but the "
                "packaging table is no longer in the database. Set their 'Unit / Packaging' by hand "
                "(column product_pricelist_item.packaging_id kept for reference).", count)
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("""
        SELECT item.id, pack.name, pack.qty, pack.product_id
          FROM product_pricelist_item item
          JOIN product_packaging pack ON pack.id = item.packaging_id
         WHERE item.packaging_id IS NOT NULL AND item.uom_id IS NULL
    """)
    rows = cr.fetchall()
    Uom = env['uom.uom'].with_context(active_test=False)
    moved, unmatched = 0, []
    for item_id, name, qty, product_id in rows:
        if isinstance(name, dict):  # translated jsonb
            name = name.get('en_US') or next(iter(name.values()), '')
        product = env['product.product'].browse(product_id).exists()
        if not product:
            unmatched.append(item_id)
            continue
        target_factor = (qty or 0.0) * product.uom_id.factor
        candidates = Uom.search([('name', '=ilike', name)])
        candidates = candidates.filtered(lambda u: abs(u.factor - target_factor) < 1e-6)
        preferred = candidates & product.uom_ids
        uom = (preferred or candidates)[:1]
        if not uom:
            unmatched.append(item_id)
            continue
        env['product.pricelist.item'].browse(item_id).uom_id = uom
        moved += 1
    _logger.info("sales_pricelist_advanced: %s packaging rule(s) moved to their packaging unit.", moved)
    if unmatched:
        _logger.warning(
            "sales_pricelist_advanced: no matching unit found for the packaging of pricelist rule(s) %s; "
            "set their 'Unit / Packaging' by hand.", unmatched)
