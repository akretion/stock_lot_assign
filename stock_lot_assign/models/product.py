# -*- coding: utf-8 -*-

from openerp import models, fields, api
from openerp.tools import float_compare


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.multi
    def _available_lot_ids(self):
        """ free (not reserved) quantity """
        all_lot_ids = []
        for product in self:
            lot_ids = self.env['stock.production.lot'].search(
                [['product_id', '=', product.id]])
            for lot in lot_ids:
                if float_compare(
                    lot.with_context(self._context).stock_available, 0,
                    precision_rounding=product.uom_id.rounding) > 0:
                    all_lot_ids.append((lot, lot.stock_available,
                                        lot.stock_reserved))
        return all_lot_ids

    @api.multi
    def _all_available_lot_ids(self):
        """ reserved + free """
        all_lot_ids = []
        for product in self:
            lot_ids = self.env['stock.production.lot'].search(
                [['product_id', '=', product.id]])
            for lot in lot_ids:
                if float_compare(
                    lot.with_context(self._context).stock_all_available, 0,
                    precision_rounding=product.uom_id.rounding) > 0:
                    all_lot_ids.append((lot, lot.stock_all_available,
                                        lot.stock_all_reserved))
        return all_lot_ids

