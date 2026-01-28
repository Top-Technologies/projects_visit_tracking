from odoo import models, fields, api


class VisitTracker(models.Model):
    _name = 'visit.tracker'
    _description = 'Salesperson Visit Tracker'
    _order = 'visit_date desc'

    user_id = fields.Many2one(
        'res.users', string='Salesperson',
        default=lambda self: self.env.user, required=True, readonly=True
    )
    lead_id = fields.Many2one(
        'crm.lead', string='Lead/Opportunity',
        help='The CRM lead or opportunity this visit is related to'
    )
    partner_id = fields.Many2one('res.partner', string='Customer')
    visit_date = fields.Datetime(
        string='Visit Date', default=fields.Datetime.now,
        required=True, readonly=True
    )
    latitude = fields.Float(string='Latitude', digits=(10, 7), readonly=True)
    longitude = fields.Float(string='Longitude', digits=(10, 7), readonly=True)
    device_info = fields.Char(string='Device Info', readonly=True)
    location_address = fields.Char(
        string='Address', readonly=True,
        help='Address of check-in location'
    )
    notes = fields.Text(string='Visit Notes', help='Additional notes about this visit')
    maps_url = fields.Char(
        string='Map Link', compute='_compute_maps_url', store=False
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Checked In'),
    ], string='Status', default='draft', readonly=True)

    @api.depends('latitude', 'longitude')
    def _compute_maps_url(self):
        for record in self:
            if record.latitude and record.longitude:
                record.maps_url = (
                    f'https://www.openstreetmap.org/'
                    f'?mlat={record.latitude}&mlon={record.longitude}'
                )
            else:
                record.maps_url = False

    def action_check_in(self, lat, long, device_info, address=False):
        """Method called by JS to save location"""
        for record in self:
            record.write({
                'latitude': lat,
                'longitude': long,
                'device_info': device_info,
                'location_address': address,
                'visit_date': fields.Datetime.now(),
                'state': 'done'
            })
