========================
Advanced Sales Pricelist
========================

Odoo 19 (Community & Enterprise). Pricelist rules per **unit** and per
**packaging**, percentage extra fees, Excel bulk import and quantity
conversion on sales order lines.

In Odoo 19 a packaging is a unit of measure (e.g. *Carton of 24* = 24 Units)
listed in the product's **Packagings**. A sales order line sold in *Carton of
24* has that unit, and its unit price is a price per carton.

Configuration
=============
* Sales > Configuration > Settings: enable *Pricelists* and *Units &
  Packagings*.
* Create the packagings (Sales > Configuration > Units & Packagings) and add
  them to the products (product form, *Packagings*).
* Two company options appear next to the pricelist setting:

  * **Keep Quantity on UoM Change** – 24 Units become 2 Dozens or 1 Carton of
    24 when the line unit changes (default: on).
  * **Round Up to Whole Packages** – a line sold in a packaging gets a whole
    number of packages: 30 Units -> 1.25 -> 2 Cartons (default: on).

Rules
=====
A pricelist rule gets an optional **Unit / Packaging** condition, on any scope
(variant, product, category, global). The rule matches only lines sold in that
unit. Fixed price, extra fee, margins, rounding and minimum quantity are
expressed **in that unit / per package**. On product rules the choice is the
product unit and its packagings; the unit must be convertible into the product
unit.

Priority: the standard scope order is kept (variant > product > category >
global). Inside the same scope: unit / packaging rules > generic rules, then
min. quantity (desc), as in standard Odoo. Lines that match no unit rule fall
back to the standard rules (a carton then costs 24 x the unit price).

Works with fixed prices, discounts and formulas, the Odoo 18+ discount display
(only *Discount* rules show a discount, when the *Discounts* setting is on),
rules based on another pricelist (the unit is propagated) and pricelists in a
foreign currency.

Percentage extra fee (formula rules)
====================================
Next to the fixed *Extra Fee*, formula rules get **Extra Fee (%)** and
**Extra Fee (%) On**:

* *Base Price* – percentage of the price the rule is based on (sales price,
  cost or other pricelist);
* *Discounted Price* – percentage of the price after discount and rounding.

Same position as the fixed fee in Odoo's formula: discount (or markup on cost)
-> rounding -> fixed fee + percentage fee -> min/max margins. A negative value
is a rebate. On unit / packaging rules the fee is computed per package. The
Point of Sale applies it too (``sales_pricelist_pos_advanced``).

Example: Sales Price 100, discount 10 %, fee 5 % on Base Price -> 95.00;
fee 5 % on Discounted Price -> 94.50.

Bulk import (Excel templates)
=============================
Sales > Products > **Pricelist Rules** lists the rules of all pricelists in an
editable grid. Templates are offered in the gear menu (⚙) > *Import records*:

=====================================================================  ===============
Template                                                               Import from
=====================================================================  ===============
Pricelist rules - Fixed prices (product, unit, packaging)              Pricelist Rules
Pricelist rules - All rule types (discounts, formulas)                 Pricelist Rules
Pricelists with rules - Fixed prices (product, unit, packaging)        Pricelists
Pricelists with rules - All rule types (discounts, formulas)           Pricelists
=====================================================================  ===============

* Headers are technical names, mapped automatically in every language.
  Choice columns have drop-down lists; each header has a note; a bilingual
  (English / Arabic) *Instructions* sheet explains every column and example.
* Units and packagings are given by name in ``uom_id`` (e.g. *Carton of 24*).
* Empty cells keep the defaults (Based on = Sales Price, Extra Fee (%) On =
  Base Price, currency = company currency).
* The same four files are copied in ``excel_templates/`` for direct use (not
  loaded by the module).

Upgrade from Odoo 18
====================
Odoo 19 removed product packagings (``product.packaging``). A migration script
moves rules that targeted a packaging to the unit with the same name and
quantity, when the old data is still in the database, and logs the rules it
could not match so their *Unit / Packaging* can be set by hand.

Fixes of standard behaviour
===========================
* A minimum margin can be set without a maximum margin (Odoo rejects it
  although the engine treats a 0 maximum as "no maximum").
* Category rules created by import or code open with "Category" selected.

Developer API::

    pricelist._get_product_price(product, 2, uom=carton)

Notes
=====
* Point of Sale order lines are always in the product unit (a packaging
  barcode adds its quantity in that unit): install
  ``sales_pricelist_pos_advanced`` (auto-installed when POS is present) so
  unit / packaging rules are never sent to the POS.

Tests::

    odoo-bin -d <db> -i sales_pricelist_advanced --test-enable --test-tags /sales_pricelist_advanced
