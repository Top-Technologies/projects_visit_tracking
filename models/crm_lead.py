from odoo import models, fields, api


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    visit_tracker_ids = fields.One2many(
        'visit.tracker', 'lead_id', string='Visit Trackers'
    )
    visit_count = fields.Integer(
        string='Visits', compute='_compute_visit_count'
    )

    @api.depends('visit_tracker_ids')
    def _compute_visit_count(self):
        for record in self:
            record.visit_count = len(record.visit_tracker_ids)

    def action_view_visits(self):
        """Open visit tracker records for this lead"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Visits',
            'res_model': 'visit.tracker',
            'view_mode': 'list,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {'default_lead_id': self.id},
        }

    def action_check_in(self, lat, long, device_info, address=False):
        """Create a visit tracker record and mark it as checked in"""
        self.ensure_one()
        
        # Create the visit record first (in draft state)
        visit = self.env['visit.tracker'].create({
            'lead_id': self.id,
            'partner_id': self.partner_id.id if self.partner_id else False,
            'latitude': lat,
            'longitude': long,
            'device_info': device_info,
            'state': 'draft',
        })
        
        # Call the visit tracker's action_check_in to handle address lookup
        # This ensures the server-side geocoding is used
        visit.action_check_in(lat, long, device_info, address)
        
        return visit.id
