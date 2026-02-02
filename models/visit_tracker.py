from odoo import _, models, fields, api
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)


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
        ('cancellation_requested', 'Cancellation Requested'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', readonly=True)

    cancellation_reason = fields.Text(
        string='Cancellation Reason',
        help='Reason given by the salesperson for requesting cancellation'
    )
    cancellation_request_date = fields.Datetime(
        string='Cancellation Requested On', readonly=True
    )
    cancelled_by_id = fields.Many2one(
        'res.users', string='Cancelled By', readonly=True,
        help='User (manager) who approved the cancellation'
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        help='Reason given by the manager when rejecting the cancellation request'
    )

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
            # If no address provided, try to get it via reverse geocoding on server side
            if not address and lat and long:
                address = self._get_address_from_coordinates(lat, long)
            
            record.write({
                'latitude': lat,
                'longitude': long,
                'device_info': device_info,
                'location_address': address,
                'visit_date': fields.Datetime.now(),
                'state': 'done'
            })

    @api.model
    def _get_address_from_coordinates(self, latitude, longitude):
        """
        Perform reverse geocoding using Nominatim from the server side.
        This avoids CORS issues when calling from JavaScript.
        """
        try:
            url = (
                f'https://nominatim.openstreetmap.org/reverse'
                f'?format=json&lat={latitude}&lon={longitude}'
                f'&zoom=18&addressdetails=1'
            )
            headers = {
                'User-Agent': 'OdooVisitTracker/1.0 (your-email@example.com)'
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('display_name', False)
            else:
                _logger.warning(
                    f"Nominatim returned status {response.status_code}"
                )
        except Exception as e:
            _logger.warning(f"Reverse geocoding failed: {e}")
        return False

    def action_request_cancellation(self):
        """Salesperson requests cancellation of their visit. Only the visit owner can request."""
        for record in self:
            if record.state != 'done':
                continue
            if record.user_id != self.env.user:
                raise UserError(
                    _('Only the salesperson who recorded this visit can request its cancellation.')
                )
            record.write({
                'state': 'cancellation_requested',
                'cancellation_request_date': fields.Datetime.now(),
            })

    def action_approve_cancellation(self):
        """Sales manager approves the cancellation request."""
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_('Only sales managers can approve cancellation requests.'))
        for record in self:
            if record.state != 'cancellation_requested':
                continue
            record.write({
                'state': 'cancelled',
                'cancelled_by_id': self.env.user.id,
                'rejection_reason': False,
            })

    def action_reject_cancellation(self):
        """Sales manager rejects the cancellation request. Visit returns to Checked In."""
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_('Only sales managers can reject cancellation requests.'))
        for record in self:
            if record.state != 'cancellation_requested':
                continue
            record.write({
                'state': 'done',
                'cancelled_by_id': False,
                'cancellation_request_date': False,
            })
