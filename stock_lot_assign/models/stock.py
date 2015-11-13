# -*- coding: utf-8 -*-

from openerp import models, fields, api
import openerp.addons.decimal_precision as dp
from openerp.tools import float_compare
from openerp.tools.translate import _
from openerp.osv import osv


# NOTE the code in this class could go in the core or in another module
class stock_production_lot(osv.osv):
    _inherit = 'stock.production.lot'

    @api.one
    def _get_stock(self): # TODO make it work for multiple ids in a single query; how?
        query = """SELECT sum(qty), lot_id, reservation_id FROM stock_quant, stock_location WHERE stock_location.id = stock_quant.location_id
                    AND stock_location.usage = 'internal' AND lot_id in %s GROUP BY lot_id, reservation_id"""
        params = (tuple([self.id]),) # TODO tuple(ids)
        self._cr.execute(query, params)
        results = self._cr.fetchall()
        
        reserved = 0.0
        free = 0.0

        for qty, lot, reservation in results:
            if reservation:
                reserved += qty
            else:
                free += qty
        self.stock_all_available = reserved + free
        self.stock_all_reserved = reserved
        self.stock_all_free = free

        location_id = self._context.get("location_id", self._context.get("loc_orig_id", False))
        if location_id:
            query = 'SELECT sum(qty), lot_id, reservation_id FROM stock_quant WHERE stock_quant.location_id = %s AND lot_id in %s GROUP BY lot_id, reservation_id'
            params = (location_id, tuple([self.id])) # TODO tuple(ids)
            self._cr.execute(query, params)
            results = self._cr.fetchall()
        
            reserved = 0.0
            free = 0.0

            for qty, lot, reservation in results:
                if reservation:
                    reserved += qty
                else:
                    free += qty
            self.stock_available = reserved + free
            self.stock_reserved = reserved
            self.stock_free = free
        else:
            self.stock_available = self.stock_all_available
            self.stock_reserved = self.stock_all_reserved
            self.stock_free = self.stock_all_free


    stock_available = fields.Float(
        string='Available Qty', multi='stock',
        digits=dp.get_precision('Product Unit of Measure'),
        readonly=True, compute='_get_stock')

    stock_reserved = fields.Float(
        string='Reserved Qty', multi='stock',
        digits=dp.get_precision('Product Unit of Measure'),
        readonly=True, compute='_get_stock')

    stock_free = fields.Float(
        string='Free Qty', multi='stock',
        digits=dp.get_precision('Not Reserved Qty'),
        readonly=True, compute='_get_stock')

    stock_all_available = fields.Float(
        string='All Available Qty', multi='stock',
        digits=dp.get_precision('Product Unit of Measure'),
        readonly=True, compute='_get_stock')

    stock_all_reserved = fields.Float(
        string='All Reserved Qty', multi='stock',
        digits=dp.get_precision('Product Unit of Measure'),
        readonly=True, compute='_get_stock')

    stock_all_free = fields.Float(
        string='All Free Qty', multi='stock',
        digits=dp.get_precision('Not Reserved Qty'),
        readonly=True, compute='_get_stock')


    @api.one
    def _get_reservation_names(self):
        """
        returns string with lists of picking names separated by a comma
        """
        location_id = self._context.get("location_id", self._context.get("loc_orig_id", False))
        d = {'stock_all_reservation_detail':False,'stock_reservation_detail':location_id}

        for k in d: 
            reser = self._get_reservation_ids(d[k])
            reser = reser and reser[0]
            p = {}
            n = []
            for r in reser:
                name = r.name or '-'
                if r.picking_id and p.get(r.picking_id.id,True):
                    p[r.picking_id.id] = False
                    name = r.picking_id.name or '-'
                n.append(name)
            self[k] = ", ".join([i for i in n])
            
    @api.one
    def _get_reservation_ids(self, location_id=False): # TODO filtrar tambe el location_id, si cal
        """
        returns list of stock.move objects
        """
        if location_id:
            dm = [('lot_id', '=', self.id), ('reservation_id', '!=', False), ('location_id', '=', location_id)]
        else:
            dm = [('lot_id', '=', self.id), ('reservation_id', '!=', False)] 
        quants = self.env['stock.quant'].search(dm)
        reser1 = [q.reservation_id for q in quants]
        d = {}
        #reser = list(set(reser1)) #eliminem repetits
        reser = [ d.setdefault(x,x) for x in reser1 if x not in d ] #eliminem repetits
        return reser

    stock_reservation_detail = fields.Char(
        string='Pickings', multi='stock_details',
        readonly=True, compute='_get_reservation_names')

    stock_all_reservation_detail = fields.Char(
        string='All Pickings', multi='stock_details',
        readonly=True, compute='_get_reservation_names')


class PackOperations(models.Model):
    _inherit = "stock.pack.operation"

    @api.one
    @api.depends('lot_id')
    def _compute_available(self):
        if self.lot_id:
            self.stock_available = self.lot_id.stock_available

    @api.one
    @api.depends('lot_id')
    def _compute_reserved(self):
        if self.lot_id:
            self.stock_reserved = self.lot_id.stock_reserved

    stock_available = fields.Float(
        string='Available Qty',
        digits=dp.get_precision('Product Unit of Measure'),
        readonly=True, compute='_compute_available')
    stock_reserved = fields.Float(
        string='Reserved Qty',
        digits=dp.get_precision('Product Unit of Measure'),
        readonly=True, compute='_compute_reserved')
    move_id = fields.Many2one('stock.move', 'Stock Move')


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.one
    @api.depends('reserved_quant_ids')
    def _compute_missing(self):
        self.stock_missing = self.product_uom_qty
        for quant in self.reserved_quant_ids:
            if quant.lot_id:
                self.stock_missing -= quant.qty

    @api.one
    def _has_ancestor(self):
        ancestors = self.search([('move_dest_id', '=', self.id)])
        self.has_ancestor = ancestors and True or False

    @api.one
    @api.depends('picking_id.pack_operation_ids')
    def _compute_lots(self):
       print "------- picking_id.pack_operation_ids", self.picking_id.pack_operation_ids
       self.lots_info = ""
       lots_dict = {}
       for quant in self.reserved_quant_ids:
           if not lots_dict.get(quant.lot_id.name):
               lots_dict[quant.lot_id.name] = 0
           lots_dict[quant.lot_id.name] += quant.qty
           print "reserved quants", lots_dict
       if not lots_dict:
           for link in self.linked_move_operation_ids:
               print "\nlink", link, link.read()
               pack = link.operation_id
               print "OP", pack, pack.read()
               if not lots_dict.get(pack.lot_id.name):
                   lots_dict[pack.lot_id.name] = 0
               lots_dict[pack.lot_id.name] += link.qty
               print "linked_move_operation_ids", lots_dict
       if not lots_dict:
           prev_move_ids = self.search([('move_dest_id', '=', self.id)])
           if prev_move_ids and prev_move_ids[0].picking_id:
               prev_move = prev_move_ids[0]
               for pack in prev_move_ids[0].picking_id.pack_operation_ids:
                   if pack.product_id.id == prev_move.product_id.id and pack.product_qty > 0:
                       if not lots_dict.get(pack.lot_id.name):
                           lots_dict[pack.lot_id.name] = 0
                       lots_dict[pack.lot_id.name] += pack.product_qty
               print "prev move", lots_dict 
                       #self.lots_info += "%s_(%s)\n" % (pack.lot_id.name, pack.product_qty)

       for k,v in lots_dict.iteritems():
           self.lots_info += "%s_(%s)\n" % (k or "NO_LOT", v)

    stock_missing = fields.Float(
        string='Qty to reserve',
        digits=dp.get_precision('Product Unit of Measure'),
        readonly=True, compute='_compute_missing')

    has_ancestor = fields.Boolean(
        string='Has Ancestor',
        readonly=True, compute='_has_ancestor')

    lots_info = fields.Char(string='Lots',
        compute='_compute_lots') # TODO + store + index?

    price_unit = fields.Float(
        'Unit Price', help="Technical field used to record the product cost set by the user during a picking confirmation (when costing method used is 'average price' or 'real'). Value given in company currency and in product uom.", required=True,
        digits=dp.get_precision('Product Price'), default=0.0)

    def _get_invoice_line_vals(self, cr, uid, move, partner,
                               inv_type, context=None):

        result = super(StockMove, self)._get_invoice_line_vals(
            cr, uid, move, partner, inv_type, context)

        if move.location_dest_id.usage == 'transit':
            result['price_unit'] = float(move.price_unit / 0.96)
        else:
            result['price_unit'] = move.price_unit
        return result


class StockMoveSplitLines(models.TransientModel):
    _name = "stock.move.split.lines"
    _description = "Stock move Split lines"
    _order = 'lot_id'

    quantity = fields.Float(
        'Quantity',
        digits_compute=dp.get_precision('Product Unit of Measure'), default=0.0)
    wizard_id = fields.Many2one('stock.move.split', 'Parent Wizard')
    lot_id = fields.Many2one('stock.production.lot', 'Lot', readonly=True)
    
    @api.one
    @api.depends('lot_id')
    def _compute_qtys(self):
        if self.lot_id:
            self.stock_available = self.lot_id.stock_available
            self.stock_reserved = self.lot_id.stock_reserved
            self.stock_reservable = self.stock_available - self.stock_reserved
    
    """
    @api.one
    @api.depends('lot_id')
    def _compute_available(self):
        if self.lot_id:
            self.stock_available = self.lot_id.stock_available

    @api.one
    @api.depends('lot_id')
    def _compute_reserved(self):
        if self.lot_id:
            self.stock_reserved = self.lot_id.stock_reserved
    
    @api.one
    @api.depends('stock_available', 'stock_reserved')
    def _compute_reservable(self):
        if self.lot_id:
            self.stock_reservable = self.stock_available - self.stock_reserved
            return self.stock_reservable
            #self.stock_reservable = self.lot_id.stock_available - self.lot_id.stock_reserved
    """

    @api.one
    @api.depends('lot_id')
    def _compute_reservation_detail(self):
        if self.lot_id:
            self.stock_reservation_detail = self.lot_id.stock_reservation_detail

        
    stock_available = fields.Float(
        string='Available Qty', multi='stock',
        digits=dp.get_precision('Product Unit of Measure'),
        readonly=True, compute='_compute_qtys')
    stock_reserved = fields.Float(
        string='Reserved Qty', multi='stock',
        digits=dp.get_precision('Product Unit of Measure'),
        readonly=True, compute='_compute_qtys')
    stock_reservable = fields.Float(
        string='Reservable Qty', multi='stock',
        digits=dp.get_precision('Product Unit of Measure'),
        readonly=True, compute='_compute_qtys')

    stock_reservation_detail = fields.Char(
        string='Pickings',
        readonly=True, compute='_compute_reservation_detail')

    all_stock = fields.Boolean(
        string='All Stock',
        readonly=True, default=False)

    @api.model
    def _default_can_create(self):
        loc_orig_id = self._context.get('loc_orig_id', 0)
        return (loc_orig_id==8) or False
        
    can_create = fields.Boolean(
        string='CanCreate',
        readonly=True, default=_default_can_create)


class StockMoveSplit(models.TransientModel):
    _name = "stock.move.split"
    _description = "Split in Serial Numbers"
    
    @api.model
    def _default_line_ids(self):
        lines = []
        if self._context.get('active_id'):
            mv = self.env['stock.move'].browse(self._context.get('active_id'))
            picking_id = mv.picking_id.id
            context2 = dict(self._context)
            context2['location_id'] = mv.location_id.id
            lots_info = self.with_context(context2)._default_product_id()._available_lot_ids()
            for lots in lots_info:
                (lot, available, reserved) = lots 
                match = False
                dm = [('picking_id', '=', picking_id), ('lot_id', '=', lot.id)]
                packs = self.env['stock.pack.operation'].search(dm)
                for pack in packs: # try to find an existing pack for move
                    if pack.linked_move_operation_ids and pack.linked_move_operation_ids[0].move_id.id == mv.id: # TODO only link 0 ?
                        lines.append((0, False, {
                            'lot_id': lot.id,
                            'quantity': pack.product_qty,
                            'stock_available': available,
                            'stock_reserved': reserved,
                            'stock_reservable': available-reserved,
                            'stock_reservation_detail': lot.stock_reservation_detail}))
                        match = True
                if not match:
                    d = {'lot_id': lot.id,
                        'stock_available': available,
                        'stock_reserved': reserved,
                        'stock_reservable': available-reserved,
                        'stock_reservation_detail': lot.stock_reservation_detail,
                        #'quantity': mv.product_qty
                        }
                    if len(lots_info) == 1: # autofill. TODO eventually we ca autofill in other cases too
                        d['quantity'] = mv.product_qty
                    lines.append((0, False, d))
        return lines

    @api.model
    def _default_line2_ids(self):
        lines = []
        if self._context.get('active_id'):
            mv = self.env['stock.move'].browse(self._context.get('active_id'))
            #picking_id = mv.picking_id.id
            context2 = dict(self._context)
            context2['location_id'] = mv.location_id.id
            lots_info = self.with_context(context2)._default_product_id()._all_available_lot_ids()
            for lots in lots_info:
                (lot, available, reserved) = lots 
                d = {'lot_id': lot.id,
                    'stock_available': available,
                    'stock_reserved': reserved,
                    'stock_reservable': available-reserved,
                    'stock_reservation_detail': lot.stock_all_reservation_detail,
                    'all_stock': True, 
                    #'quantity': mv.product_qty
                    }
                lines.append((0, False, d))
        return lines

    @api.model
    def _default_product_id(self):
        if self._context.get('active_id'):
            move = self.env['stock.move'].browse(
                self._context.get('active_id'))
            return move.product_id

    @api.model
    def _default_product_uom(self):
        if self._context.get('active_id'):
            move = self.env['stock.move'].browse(
                self._context.get('active_id'))
            return move.product_uom

    @api.model
    def _default_product_qty(self):
        if self._context.get('active_id'):
            move = self.env['stock.move'].browse(
                self._context.get('active_id'))
            return move.product_qty

    @api.model
    def _default_location_id(self):
        if self._context.get('active_id'):
            move = self.env['stock.move'].browse(
                self._context.get('active_id'))
            return move.location_id

    @api.model
    def _default_move_id(self):
        return self._context.get('active_id', False)


    move_id = fields.Many2one(
        'stock.move', 'Move', required=True,
        default=_default_move_id)
    product_id = fields.Many2one(
        'product.product', string='Product',
        default=_default_product_id)
    qty = fields.Float(
        string='Quantity',
        default=_default_product_qty)
    location_id = fields.Many2one(
        'stock.location', 'Location',
        readonly=True, default=_default_location_id)
    product_uom = fields.Many2one(
        'product.uom', 'Unit of Measure',
        default=_default_product_uom)
    line_ids = fields.One2many(
        'stock.move.split.lines', 'wizard_id', 'Serial Numbers',
        domain=[('all_stock', '!=', True)],
        default=_default_line_ids)
    line2_ids = fields.One2many(
        'stock.move.split.lines', 'wizard_id', 'Serial Numbers',
        domain=[('all_stock', '=', True)],
        default=_default_line2_ids)
    force = fields.Boolean('Enable Superior Quantity?')


    @api.multi
    def assign(self):
        if self.move_id.picking_id:
            self.env['stock.quant'].quants_unreserve(self.move_id)
            total_assigned = 0
            for line in self.line_ids:
                total_assigned += line.quantity
                dm = [('picking_id', '=', self.move_id.picking_id.id),
                      ('lot_id', '=', line.lot_id.id)]#, ('move_id', '=', self.move_id.id)]
                packs = self.env['stock.pack.operation'].search(dm)
                op = False
                for pack in packs:
                    for link in pack.linked_move_operation_ids: # FIXME dirty nested looping
                        if link.move_id.id == self.move_id.id:
                            op = pack
                            # NOTE: we purposely skip the write logic here
                            self._cr.execute("UPDATE stock_pack_operation SET product_qty=%s WHERE ID=%s", (line.quantity, op.id))
                            break

                if not op and line.quantity > 0:
                    vals = {
                        'product_id': self.product_id.id,
                        'lot_id': line.lot_id.id,
                        'product_uom_id': self.move_id.product_uom.id,
                        'product_qty': line.quantity,
                        'picking_id': self.move_id.picking_id.id if self.move_id.picking_id else False,
                        'move_id': self.move_id.id,
                        'location_id': self.location_id.id,
                        'location_dest_id': self.move_id.location_dest_id.id}
                    op = self.env['stock.pack.operation'].create(vals)
                    print "CREATED OP move.linked_move_operation_ids 0", op, op.linked_move_operation_ids, self.move_id.linked_move_operation_ids

        # here we will clean a recreate the stock.move.operation.link because operation creation and previous assignments
        # can leave them pointing to wrong moves that would mix our reservations
        if self.move_id.picking_id:
            for op in self.move_id.picking_id.pack_operation_ids:
                if op.move_id.id == self.move_id.id:
                    self._cr.execute("DELETE from stock_move_operation_link WHERE operation_id=%s", (op.id,))
                    print "CREATE LINK", op, op.product_qty, self.move_id
                    self.env['stock.move.operation.link'].create({
                        'move_id': self.move_id.id,
                        'operation_id': op.id,
                        'qty': op.product_qty,
                    })

        if float_compare(total_assigned, self.qty, 3) > 0 and not self.force:
            raise osv.except_osv(
                _('Quantity mismatch!'),
                _("Total quantity to assign is %s but you assigned %s") % (self.qty, total_assigned))
        self.move_id.do_unreserve()
        self.move_id.action_assign()

        dummy, view_id = self.pool.get('ir.model.data').get_object_reference(
            self._cr, self._uid, 'stock', 'view_picking_form')
        if self._context.get('indirect_move'):
            return {'type': 'ir.actions.act_window_close'}
        else:
            return {
                'name': _('Picking'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'stock.picking',
                'view_id': view_id,
                'res_id': self.move_id.picking_id.id,
                'context': self._context,
            }

