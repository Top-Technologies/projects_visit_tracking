from odoo import _, models, fields, api
from odoo.exceptions import UserError


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    visit_tracker_ids = fields.One2many(
        'visit.tracker', 'lead_id', string='Visit Trackers'
    )
    visit_count = fields.Integer(
        string='Visits', compute='_compute_visit_count'
    )

    active_visit_id = fields.Many2one(
        'visit.tracker', compute='_compute_active_visit', readonly=True
    )
    has_active_visit = fields.Boolean(
        compute='_compute_active_visit', readonly=True
    )

    @api.depends('visit_tracker_ids')
    def _compute_visit_count(self):
        for record in self:
            record.visit_count = len(record.visit_tracker_ids)

    @api.depends('visit_tracker_ids.state', 'visit_tracker_ids.user_id')
    def _compute_active_visit(self):
        for record in self:
            active_visit = record.visit_tracker_ids.filtered(
                lambda v: v.state == 'done' and v.user_id == self.env.user
            )
            active_visit = active_visit[:1]
            record.active_visit_id = active_visit.id if active_visit else False
            record.has_active_visit = bool(active_visit)

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

        active_visit = self.env['visit.tracker'].search([
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'done'),
        ], limit=1)
        if active_visit:
            lead_name = active_visit.lead_id.display_name if active_visit.lead_id else ''
            partner_name = active_visit.partner_id.display_name if active_visit.partner_id else ''
            visit_date = active_visit.visit_date or ''
            if lead_name or partner_name:
                place = lead_name or partner_name
                if lead_name and partner_name and partner_name != lead_name:
                    place = f'{lead_name} ({partner_name})'
                raise UserError(
                    _('You are already checked in to %(place)s since %(time)s. Please check out before starting a new visit.')
                    % {'place': place, 'time': visit_date}
                )
            raise UserError(
                _('You are already checked in to another lead. Please check out before starting a new visit.')
            )
        
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

    def action_check_out(self):
        self.ensure_one()
        active_visit = self.env['visit.tracker'].search([
            ('lead_id', '=', self.id),
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'done'),
        ], order='visit_date desc', limit=1)
        if not active_visit:
            raise UserError(_('You have no active check-in on this lead.'))
        active_visit.action_check_out()
        return True
