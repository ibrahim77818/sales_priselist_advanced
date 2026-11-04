# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import TransactionCase


class AspCommon(TransactionCase):
    """Shared fixtures.

    Water Bottle: list price 10.00 / Unit, cost 6.00, packagings:
        * Pack of 6   (qty 6)
        * Carton of 24 (qty 24)
    -> list price per Dozen = 120.00, per Carton = 240.00
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        # Enough precision to assert per-unit prices derived from package prices.
        cls.env.ref('product.decimal_price').digits = 6

        cls.company = cls.env.company
        cls.currency = cls.company.currency_id
        cls.company.write({
            'asp_convert_qty_on_uom_change': True,
            'asp_round_qty_to_packaging': True,
        })
        cls.env.user.groups_id |= (
            cls.env.ref('uom.group_uom')
            | cls.env.ref('product.group_stock_packaging')
            | cls.env.ref('product.group_product_pricelist')
            | cls.env.ref('sales_team.group_sale_manager')
        )

        cls.uom_unit = cls.env.ref('uom.product_uom_unit')
        cls.uom_dozen = cls.env.ref('uom.product_uom_dozen')
        cls.uom_kg = cls.env.ref('uom.product_uom_kgm')

        cls.categ_drinks = cls.env['product.category'].create({'name': 'ASP Drinks'})
        cls.categ_food = cls.env['product.category'].create({'name': 'ASP Food'})

        cls.product = cls._create_product('ASP Water Bottle', 10.0, cost=6.0)
        cls.tmpl = cls.product.product_tmpl_id
        cls.pack_6 = cls._create_packaging(cls.product, 'Pack of 6', 6)
        cls.carton = cls._create_packaging(cls.product, 'Carton of 24', 24)

        cls.juice = cls._create_product('ASP Juice', 5.0)
        cls.juice_carton = cls._create_packaging(cls.juice, 'Juice Carton of 12', 12)

        cls.flour = cls._create_product('ASP Flour', 3.0, uom=cls.uom_kg, categ=cls.categ_food)
        cls.egg_tray = cls._create_product('ASP Egg Tray', 30.0, uom=cls.uom_dozen, categ=cls.categ_food)

        cls.partner = cls.env['res.partner'].create({'name': 'ASP Customer'})
        cls.pricelist = cls._create_pricelist('ASP Pricelist')

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def _create_product(cls, name, price, cost=0.0, uom=None, categ=None):
        uom = uom or cls.uom_unit
        return cls.env['product.product'].create({
            'name': name,
            'list_price': price,
            'standard_price': cost,
            'uom_id': uom.id,
            'uom_po_id': uom.id,
            'categ_id': (categ or cls.categ_drinks).id,
            'type': 'consu',
            'taxes_id': [Command.clear()],
        })

    @classmethod
    def _create_packaging(cls, product, name, qty):
        return cls.env['product.packaging'].create({
            'name': name,
            'product_id': product.id,
            'qty': qty,
            'sales': True,
        })

    @classmethod
    def _create_pricelist(cls, name, currency=None):
        return cls.env['product.pricelist'].create({
            'name': name,
            'currency_id': (currency or cls.currency).id,
            'company_id': False,
        })

    @classmethod
    def _enable_discount_display(cls):
        """Odoo 18 shows a pricelist discount on order lines only when the
        'Discounts' setting is on (checked on the superuser) and only for
        percentage rules."""
        cls.env.ref('base.user_root').groups_id |= cls.env.ref('sale.group_discount_per_so_line')
        cls.env.user.groups_id |= cls.env.ref('sale.group_discount_per_so_line')

    def _item(self, pricelist=None, **vals):
        vals.setdefault('compute_price', 'fixed')
        return self.env['product.pricelist.item'].create(dict(vals, pricelist_id=(pricelist or self.pricelist).id))

    def _product_item(self, pricelist=None, product=None, **vals):
        """Template-level rule (what the basic pricelist mode creates)."""
        product = product or self.product
        return self._item(pricelist, applied_on='1_product', product_tmpl_id=product.product_tmpl_id.id, **vals)

    def _order(self, pricelist=None):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': (pricelist or self.pricelist).id,
        })

    def _line(self, order, product=None, qty=1.0, uom=None, packaging=None):
        """Create an order line. ``packaging=False`` forces no packaging,
        ``None`` lets Odoo suggest one."""
        product = product or self.product
        vals = {
            'order_id': order.id,
            'product_id': product.id,
            'product_uom_qty': qty,
            'product_uom': (uom or product.uom_id).id,
        }
        if packaging is not None:
            vals['product_packaging_id'] = packaging.id if packaging else False
        return self.env['sale.order.line'].create(vals)

    def _price(self, pricelist, product, qty, uom=None, packaging=None, **kwargs):
        if packaging is not None:
            kwargs['packaging'] = packaging
        return pricelist._get_product_price(product, qty, uom=uom, **kwargs)
