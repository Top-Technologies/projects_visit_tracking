from odoo import _, models, fields, api
from odoo.exceptions import UserError
from psycopg2 import IntegrityError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    visit_tracker_ids = fields.One2many(
        'visit.tracker', 'project_id', string='Field Check-ins'
    )
    visit_count = fields.Integer(
        string='Check-ins', compute='_compute_visit_count'
    )
    has_active_visit = fields.Boolean(
        compute='_compute_active_visit', readonly=True
    )
    active_visit_id = fields.Many2one(
        'visit.tracker', compute='_compute_active_visit', readonly=True
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

    def action_view_check_ins(self):
        """Open field check-in records for this project."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Field Check-ins',
            'res_model': 'visit.tracker',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_check_in(self, lat, long, device_info, address=False):
        """Create a visit tracker record for this project and mark it as checked in."""
        self.ensure_one()

        # Concurrency guard
        self.env.cr.execute(
            "SELECT id FROM res_users WHERE id = %s FOR UPDATE",
            (self.env.user.id,),
        )

        active_visit = self.env['visit.tracker'].search([
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'done'),
        ], limit=1)
        if active_visit:
            project_name = active_visit.project_id.display_name if active_visit.project_id else _('another project')
            visit_date = active_visit.visit_date or ''
            raise UserError(
                _('You are already checked in to %(project)s since %(time)s. Please check out before starting a new visit.')
                % {'project': project_name, 'time': visit_date}
            )

        try:
            visit = self.env['visit.tracker'].create({
                'project_id': self.id,
                'latitude': lat,
                'longitude': long,
                'device_info': device_info,
                'state': 'draft',
            })
        except IntegrityError:
            self.env.cr.rollback()
            raise UserError(_('You already have an active check-in. Please check out before checking in to another project.'))

        try:
            visit.action_check_in(lat, long, device_info, address)
        except IntegrityError:
            self.env.cr.rollback()
            raise UserError(_('You already have an active check-in. Please check out before checking in to another project.'))

        return visit.id

    def action_check_out(self, latitude=False, longitude=False):
        """Check out from the active visit on this project."""
        self.ensure_one()
        active_visit = self.env['visit.tracker'].search([
            ('project_id', '=', self.id),
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'done'),
        ], order='visit_date desc', limit=1)
        if not active_visit:
            raise UserError(_('You have no active check-in on this project.'))
        active_visit.action_check_out(latitude=latitude, longitude=longitude)
        return True
