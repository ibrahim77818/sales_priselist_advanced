========================
Advanced Sales Pricelist
========================

Odoo 16 (Community & Enterprise). Pricelist rules per **Unit of Measure** and
per **Product Packaging**, with quantity normalization on sales order lines.

Configuration
=============
* Sales > Settings > Pricing: enable *Pricelists* (either mode), *Units of
  Measure* and/or *Product Packagings*.
* Two company options appear next to the pricelist setting:

  * **Keep Quantity on UoM Change** – 24 Units become 2 Dozens when the line
    UoM changes (default: on).
  * **Round Up to Whole Packages** – selecting a packaging rounds the line
    quantity up to whole packages (default: on).

Rules
=====
A pricelist rule gets two optional, mutually exclusive conditions:

* **Unit of Measure** – any scope (variant, product, category, global). The
  rule matches only lines sold in that UoM. Fixed price, extra fee, margins
  and minimum quantity are expressed **in that UoM**.
* **Packaging** – product or variant scope only. The rule matches only lines
  using that packaging. Fixed price, extra fee, margins, rounding and minimum
  quantity are expressed **per package / in packages**.

Priority: the standard scope order is kept (variant > product > category >
global). Inside the same scope: packaging rules > UoM rules > generic rules,
then min. quantity (desc), as in standard Odoo. Lines that match no targeted
rule fall back to the standard rules / sales price.

Works with "Multiple prices per product" and "Advanced price rules", both
discount policies (included / shown to the customer), rules based on another
pricelist (the packaging is propagated) and pricelists in a foreign currency.

Percentage extra fee (formula rules)
====================================
Next to the fixed *Extra Fee*, formula rules get **Extra Fee (%)** and
**Extra Fee (%) On**:

* *Base Price* – percentage of the price the rule is based on (sales price,
  cost or other pricelist);
* *Discounted Price* – percentage of the price after discount and rounding.

Same position as the fixed fee in Odoo's formula: discount → rounding →
fixed fee + percentage fee → min/max margins. A negative value is a rebate.
On UoM / packaging rules the fee is computed per unit / per package. The
Point of Sale applies it too (``sales_pricelist_pos_advanced``).

Example: Sales Price 100, discount 10 %, fee 5 % on Base Price → 95.00;
fee 5 % on Discounted Price → 94.50.

Note: rounding happens *before* fees. For "cost + 25 % rounded to 0.50" use a
discount of -25 % with rounding 0.50, not a percentage fee.

Bulk import (Excel templates)
=============================
Sales > Products > **Pricelist Rules** lists the rules of all pricelists in an
editable grid (formula columns are optional columns in advanced mode).
Templates are offered in *Favorites > Import records* (link "Import Template"):

=============================================  =====================  ==========================
Template                                       Import from            Pricelist mode
=============================================  =====================  ==========================
Pricelist rules - Multiple prices per product  Pricelist Rules        Multiple prices per product
Pricelist rules - Advanced price rules         Pricelist Rules        Advanced price rules
Pricelists with rules - Multiple prices ...    Pricelists             Multiple prices per product
Pricelists with rules - Advanced price rules   Pricelists             Advanced price rules
=============================================  =====================  ==========================

* "Pricelist rules" templates add rules to existing pricelists; "Pricelists
  with rules" templates create pricelists and their rules (one row per rule,
  pricelist columns on the first row of each pricelist).
* Headers are technical names, mapped automatically in every language.
  Choice columns have drop-down lists; each header has a note; a bilingual
  (English / Arabic) *Instructions* sheet explains every column and example.
* Packagings are given by name in ``packaging_name`` and searched among the
  packagings of the row's product, so the same packaging name can exist on
  many products.
* Empty cells keep the defaults (Based on = Sales Price, Extra Fee (%) On =
  Base Price, currency = company currency, discount included in the price).
* The import screen shows each template with its own name (Odoo 16 labels
  every template "Download Template"; this module displays the real label).
* The same four files are copied in ``excel_templates/`` at the root of the
  module for direct use. That folder is not referenced by the manifest and has
  no effect on installation or upgrades.

Fixes of standard behaviour
===========================
* A minimum margin can be set without a maximum margin (Odoo 16 rejected it
  although the engine treats a 0 maximum as "no maximum").
* Odoo 16 core Arabic translation of the import warning "Found multiple
  matches ..." is malformed and turns that warning into an import error for
  Arabic users. Use Internal References for products; packagings are not
  affected thanks to ``packaging_name``.

Developer API::

    pricelist._get_product_price(product, 48, packaging=carton)
    pricelist._get_product_price(product, 2, uom=dozen)
    pricelist.with_context(asp_packaging_id=carton.id)._get_product_rule(...)

Notes
=====
* Unit prices are stored with the *Product Price* decimal accuracy. A package
  price not divisible by the package quantity (200 / 24) needs 4+ decimals to
  keep exact subtotals; the line shows a notification when a gap occurs.
* Point of Sale computes prices in the browser and has no packaging context:
  install ``sales_pricelist_pos_advanced`` (auto-installed when POS is
  present) so targeted rules are never sent to the POS.

Tests::

    odoo-bin -d <db> -i sales_pricelist_advanced --test-enable --test-tags /sales_pricelist_advanced
