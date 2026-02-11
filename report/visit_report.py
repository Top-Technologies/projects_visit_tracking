from odoo import api, fields, models, tools


class VisitReport(models.Model):
    _name = 'visit.report'
    _description = 'Unified Visit Analysis & Planned vs Actual'
    _auto = False
    _order = 'report_date desc, user_id'

    # Dimensions
    user_id = fields.Many2one('res.users', string='Salesperson', readonly=True)
    report_date = fields.Date(string='Date', readonly=True)
    lead_id = fields.Many2one('crm.lead', string='Lead', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    team_id = fields.Many2one('crm.team', string='Sales Team', readonly=True)

    # Planned metrics (from route)
    planned_visits = fields.Integer(string='Planned Visits', readonly=True)
    planned_duration = fields.Float(string='Planned Duration (min)', readonly=True)

    # Actual metrics (from visit.tracker)
    actual_visits = fields.Integer(string='Actual Visits', readonly=True)
    actual_duration = fields.Float(string='Actual Duration (min)', readonly=True)

    # Variance metrics (computed in the view)
    visit_variance = fields.Integer(string='Visit Variance', readonly=True)
    duration_variance = fields.Float(string='Duration Variance (min)', readonly=True)
    visit_completion_rate = fields.Float(string='Visit Completion (%)', readonly=True)

    lead_count = fields.Integer(string='Leads', readonly=True)
    opportunity_count = fields.Integer(string='Opportunities', readonly=True)
    won_count = fields.Integer(string='Won Opportunities', readonly=True)
    lead_to_opportunity_rate = fields.Float(string='Lead to Opportunity (%)', readonly=True, group_operator='avg')
    opportunity_to_won_rate = fields.Float(string='Opportunity to Won (%)', readonly=True, group_operator='avg')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    ROW_NUMBER() OVER () AS id,
                    user_id,
                    report_date,
                    lead_id,
                    partner_id,
                    team_id,
                    SUM(planned_visits) AS planned_visits,
                    SUM(planned_duration) AS planned_duration,
                    SUM(actual_visits) AS actual_visits,
                    SUM(actual_duration) AS actual_duration,
                    SUM(actual_visits) - SUM(planned_visits) AS visit_variance,
                    SUM(actual_duration) - SUM(planned_duration) AS duration_variance,
                    CASE 
                        WHEN SUM(planned_visits) > 0 
                        THEN ROUND((SUM(actual_visits)::numeric / SUM(planned_visits)::numeric) * 100, 2)
                        ELSE 0 
                    END AS visit_completion_rate,
                    SUM(lead_count) AS lead_count,
                    SUM(opportunity_count) AS opportunity_count,
                    SUM(won_count) AS won_count,
                    CASE
                        WHEN SUM(lead_count) > 0
                        THEN ROUND((SUM(opportunity_count)::numeric / SUM(lead_count)::numeric) * 100, 2)
                        ELSE 0
                    END AS lead_to_opportunity_rate,
                    CASE
                        WHEN SUM(opportunity_count) > 0
                        THEN ROUND((SUM(won_count)::numeric / SUM(opportunity_count)::numeric) * 100, 2)
                        ELSE 0
                    END AS opportunity_to_won_rate
                FROM (
                    -- PLANNED VISITS (from Routes)
                    SELECT
                        vr.user_id,
                        vr.route_date AS report_date,
                        vrl.lead_id,
                        l.partner_id,
                        l.team_id,
                        1 AS planned_visits,
                        COALESCE(vrl.estimated_duration_minutes, 0) AS planned_duration,
                        0 AS actual_visits,
                        0 AS actual_duration,
                        CASE WHEN l.type = 'lead' THEN 1 ELSE 0 END AS lead_count,
                        CASE WHEN l.type = 'opportunity' THEN 1 ELSE 0 END AS opportunity_count,
                        CASE WHEN l.type = 'opportunity' AND cs.is_won = TRUE THEN 1 ELSE 0 END AS won_count
                    FROM visit_route_line vrl
                    JOIN visit_route vr ON vr.id = vrl.route_id
                    LEFT JOIN crm_lead l ON l.id = vrl.lead_id
                    LEFT JOIN crm_stage cs ON cs.id = l.stage_id
                    
                    UNION ALL
                    
                    -- ACTUAL VISITS (from Tracker)
                    SELECT
                        vt.user_id,
                        DATE(vt.visit_date AT TIME ZONE 'UTC') AS report_date,
                        vt.lead_id,
                        vt.partner_id,
                        l.team_id,
                        0 AS planned_visits,
                        0 AS planned_duration,
                        1 AS actual_visits,
                        COALESCE(vt.duration_minutes, 0) AS actual_duration,
                        CASE WHEN l.type = 'lead' THEN 1 ELSE 0 END AS lead_count,
                        CASE WHEN l.type = 'opportunity' THEN 1 ELSE 0 END AS opportunity_count,
                        CASE WHEN l.type = 'opportunity' AND cs.is_won = TRUE THEN 1 ELSE 0 END AS won_count
                    FROM visit_tracker vt
                    LEFT JOIN crm_lead l ON l.id = vt.lead_id
                    LEFT JOIN crm_stage cs ON cs.id = l.stage_id
                    WHERE vt.state NOT IN ('draft', 'cancelled')
                ) combined
                GROUP BY user_id, report_date, lead_id, partner_id, team_id
            )
        """ % self._table)
