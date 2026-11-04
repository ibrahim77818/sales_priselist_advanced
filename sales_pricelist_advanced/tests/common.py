# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import TransactionCase


class AspCommon(TransactionCase):
    """Shared fixtures (Odoo 19: packagings are units of measure).

    Water Bottle: list price 10.00 / Unit, cost 6.00, packagings (uom_ids):
        * Pack of 6    (6 Units)
        * Carton of 24 (24 Units)
        * Dozens       (12 Units)
    -> list price per Dozen = 120.00, per Carton = 240.00
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        cls.company = cls.env.company
        cls.currency = cls.company.currency_id
        cls.company.write({
            'asp_convert_qty_on_uom_change': True,
            'asp_round_qty_to_packaging': True,
        })
        cls.env.user.group_ids |= (
            cls.env.ref('uom.group_uom')
            | cls.env.ref('product.group_product_pricelist')
            | cls.env.ref('sales_team.group_sale_manager')
        )

        Uom = cls.env['uom.uom']
        cls.uom_unit = cls.env.ref('uom.product_uom_unit')
        cls.uom_dozen = cls.env.ref('uom.product_uom_dozen')
        cls.uom_dozen.active = True
        cls.uom_kg = cls.env.ref('uom.product_uom_kgm')
        cls.pack_6 = cls.env.ref('uom.product_uom_pack_6')
        cls.carton = Uom.create({'name': 'ASP Carton of 24', 'relative_factor': 24,
                                 'relative_uom_id': cls.uom_unit.id})
        cls.juice_carton = Uom.create({'name': 'ASP Carton of 12', 'relative_factor': 12,
                                       'relative_uom_id': cls.uom_unit.id})

        cls.categ_drinks = cls.env['product.category'].create({'name': 'ASP Drinks'})
        cls.categ_food = cls.env['product.category'].create({'name': 'ASP Food'})

        cls.product = cls._create_product('ASP Water Bottle', 10.0, cost=6.0,
                                          packagings=cls.pack_6 | cls.carton | cls.uom_dozen)
        cls.tmpl = cls.product.product_tmpl_id
        cls.juice = cls._create_product('ASP Juice', 5.0, packagings=cls.juice_carton | cls.uom_dozen)
        cls.flour = cls._create_product('ASP Flour', 3.0, uom=cls.uom_kg, categ=cls.categ_food)
        cls.egg_tray = cls._create_product('ASP Egg Tray', 30.0, uom=cls.uom_dozen, categ=cls.categ_food)

        cls.partner = cls.env['res.partner'].create({'name': 'ASP Customer'})
        cls.pricelist = cls._create_pricelist('ASP Pricelist')

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def _create_product(cls, name, price, cost=0.0, uom=None, categ=None, packagings=None):
        uom = uom or cls.uom_unit
        return cls.env['product.product'].create({
            'name': name,
            'list_price': price,
            'standard_price': cost,
            'uom_id': uom.id,
            'uom_ids': [Command.set(packagings.ids if packagings else [])],
            'categ_id': (categ or cls.categ_drinks).id,
            'type': 'consu',
            'taxes_id': [Command.clear()],
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
        """Odoo 18+ shows a pricelist discount on order lines only when the
        'Discounts' setting is on (checked on the superuser) and only for
        percentage rules."""
        cls.env.ref('base.user_root').group_ids |= cls.env.ref('sale.group_discount_per_so_line')
        cls.env.user.group_ids |= cls.env.ref('sale.group_discount_per_so_line')

    def _item(self, pricelist=None, **vals):
        vals.setdefault('compute_price', 'fixed')
        return self.env['product.pricelist.item'].create(dict(vals, pricelist_id=(pricelist or self.pricelist).id))

    def _product_item(self, pricelist=None, product=None, **vals):
        """Template-level rule."""
        product = product or self.product
        return self._item(pricelist, applied_on='1_product', product_tmpl_id=product.product_tmpl_id.id, **vals)

    def _order(self, pricelist=None):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': (pricelist or self.pricelist).id,
        })

    def _line(self, order, product=None, qty=1.0, uom=None):
        product = product or self.product
        return self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': product.id,
            'product_uom_qty': qty,
            'product_uom_id': (uom or product.uom_id).id,
        })

    def _price(self, pricelist, product, qty, uom=None, **kwargs):
        return pricelist._get_product_price(product, qty, uom=uom, **kwargs)
