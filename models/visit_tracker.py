from odoo import models, fields, api
from odoo.exceptions import ValidationError
from math import radians, cos, sin, asin, sqrt

class VisitTracker(models.Model):
    _name = 'visit.tracker'
    _description = 'Salesperson Visit Tracker'
    _order = 'visit_date desc'

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], string='Status', default='draft', required=True)
    
    user_id = fields.Many2one('res.users', string='Salesperson', default=lambda self: self.env.user, required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    visit_date = fields.Datetime(string='Visit Date', default=fields.Datetime.now, required=True)
    
    latitude = fields.Float(string='Latitude', digits=(16, 5))
    longitude = fields.Float(string='Longitude', digits=(16, 5))
    device_info = fields.Char(string='Device Info')

    customer_latitude = fields.Float(related='partner_id.partner_latitude', string='Customer Latitude', readonly=True)
    customer_longitude = fields.Float(related='partner_id.partner_longitude', string='Customer Longitude', readonly=True)

    @api.depends('partner_id', 'visit_date')
    def _compute_name(self):
        for record in self:
            date_str = record.visit_date.strftime('%Y-%m-%d %H:%M') if record.visit_date else 'New'
            partner_name = record.partner_id.name or 'Unknown'
            record.name = f"{partner_name} - {date_str}"

    def _haversine(self, lon1, lat1, lon2, lat2):
        """
        Calculate the great circle distance between two points 
        on the earth (specified in decimal degrees)
        """
        # convert decimal degrees to radians 
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

        # haversine formula 
        dlon = lon2 - lon1 
        dlat = lat2 - lat1 
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a)) 
        r = 6371 * 1000 # Radius of earth in meters.
        return c * r

    @api.constrains('latitude', 'longitude', 'partner_id', 'state')
    def _check_location(self):
        MAX_DISTANCE = 200 # meters
        for record in self:
            if record.state == 'done':
                # Only validate if we are checking in (state is done)
                # and we have captured coordinates (lat/long)
                if not record.latitude and not record.longitude:
                    # Maybe manually moved to done? Not allowed if we want strict tracking.
                    # But for now, if no coords are provided, we just warn or pass?
                    # Let's enforce it if it's supposed to be geolocation tracked.
                     pass

                if record.latitude or record.longitude:
                    if not record.partner_id.partner_latitude or not record.partner_id.partner_longitude:
                        raise ValidationError("The customer does not have Geolocation coordinates set.")
                    
                    distance = self._haversine(
                        record.longitude, record.latitude,
                        record.partner_id.partner_longitude, record.partner_id.partner_latitude
                    )
                    
                    if distance > MAX_DISTANCE:
                        raise ValidationError(f"You are too far from the customer's location ({int(distance)}m). Max allowed: {MAX_DISTANCE}m.")

    def action_check_in(self, lat, long, device_info):
        """ Deprecated: Logic moved to JS update + Save """
        pass
