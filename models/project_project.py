from odoo import _, models, fields, api
from odoo.exceptions import UserError
from psycopg2 import IntegrityError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    visit_tracker_ids = fields.One2many(
        'visit.tracker', 'project_id', string='Field Check-ins'
    )
    visit_plan_ids = fields.One2many(
        'visit.plan', 'project_id', string='Visit Plans'
    )
    visit_count = fields.Integer(
        string='Check-ins Count', compute='_compute_visit_count'
    )
    visit_plan_count = fields.Integer(
        string='Visit Plans Count', compute='_compute_plan_count'
    )
    total_planned_visit_hours = fields.Float(
        string='Planned Visit Hours', compute='_compute_visit_hours'
    )
    total_actual_visit_hours = fields.Float(
        string='Actual Visit Hours', compute='_compute_visit_hours'
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

    @api.depends('visit_plan_ids')
    def _compute_plan_count(self):
        for record in self:
            record.visit_plan_count = len(record.visit_plan_ids)

    @api.depends('visit_plan_ids.planned_hours', 'visit_tracker_ids.duration_hours', 'visit_tracker_ids.state')
    def _compute_visit_hours(self):
        for record in self:
            record.total_planned_visit_hours = sum(record.visit_plan_ids.mapped('planned_hours'))
            valid_visits = record.visit_tracker_ids.filtered(lambda v: v.state in ('done', 'checked_out'))
            record.total_actual_visit_hours = round(sum(valid_visits.mapped('duration_hours')), 2)

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
            'name': _('Check-ins: %s') % self.name,
            'res_model': 'visit.tracker',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_view_plans(self):
        """Open visit plans for this project."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Visit Plans: %s') % self.name,
            'res_model': 'visit.plan',
            'view_mode': 'list,kanban,form',
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

        # Look for approved plan for this user & project today
        today = fields.Date.context_today(self)
        approved_plan = self.env['visit.plan'].search([
            ('user_id', '=', self.env.user.id),
            ('project_id', '=', self.id),
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('state', '=', 'approved'),
        ], limit=1)

        try:
            visit = self.env['visit.tracker'].create({
                'project_id': self.id,
                'plan_id': approved_plan.id if approved_plan else False,
                'latitude': lat or 0.0,
                'longitude': long or 0.0,
                'location_address': address or False,
                'device_info': device_info or 'Manual Link / GPS',
                'state': 'draft',
            })
        except IntegrityError:
            self.env.cr.rollback()
            raise UserError(_('You already have an active check-in. Please check out before checking in to another project.'))

        try:
            visit.action_check_in(lat or 0.0, long or 0.0, device_info, address=address)
        except IntegrityError:
            self.env.cr.rollback()
            raise UserError(_('You already have an active check-in. Please check out before checking in to another project.'))

        return visit.id

    def action_check_out(self, latitude=False, longitude=False, address=False):
        """Check out from the active visit on this project."""
        self.ensure_one()
        active_visit = self.env['visit.tracker'].search([
            ('project_id', '=', self.id),
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'done'),
        ], order='visit_date desc', limit=1)
        if not active_visit:
            raise UserError(_('You have no active check-in on this project.'))
        active_visit.action_check_out(latitude=latitude, longitude=longitude, address=address)
        return True
