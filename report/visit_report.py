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
                WITH sales_users AS (
                    SELECT DISTINCT su.user_id
                    FROM (
                        SELECT user_id FROM crm_lead WHERE user_id IS NOT NULL
                        UNION
                        SELECT user_id FROM visit_route
                        UNION
                        SELECT user_id FROM visit_tracker
                    ) AS su
                    INNER JOIN res_users ru ON ru.id = su.user_id
                    WHERE ru.active = TRUE
                    UNION SELECT NULL
                ),
                combined_raw AS (
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
                        0 AS actual_duration
                    FROM visit_route_line vrl
                    JOIN visit_route vr ON vr.id = vrl.route_id
                    LEFT JOIN crm_lead l ON l.id = vrl.lead_id
                    
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
                        COALESCE(vt.duration_minutes, 0) AS actual_duration
                    FROM visit_tracker vt
                    LEFT JOIN crm_lead l ON l.id = vt.lead_id
                    WHERE vt.state NOT IN ('draft', 'cancelled')
                ),
                all_dates AS (
                    SELECT DISTINCT report_date FROM combined_raw
                    UNION
                    SELECT CURRENT_DATE
                ),
                user_dates AS (
                    SELECT u.user_id, d.report_date
                    FROM sales_users u
                    CROSS JOIN all_dates d
                ),
                grouped AS (
                    SELECT
                        cr.user_id,
                        cr.report_date,
                        NULL::integer AS lead_id,
                        NULL::integer AS partner_id,
                        MAX(cr.team_id) AS team_id,
                        SUM(cr.planned_visits) AS planned_visits,
                        SUM(cr.planned_duration) AS planned_duration,
                        SUM(cr.actual_visits) AS actual_visits,
                        SUM(cr.actual_duration) AS actual_duration,
                        SUM(cr.actual_visits) - SUM(cr.planned_visits) AS visit_variance,
                        SUM(cr.actual_duration) - SUM(cr.planned_duration) AS duration_variance,
                        CASE 
                            WHEN SUM(cr.planned_visits) > 0 
                            THEN ROUND((SUM(cr.actual_visits)::numeric / SUM(cr.planned_visits)::numeric) * 100, 2)
                            ELSE 0 
                        END AS visit_completion_rate,
                        CASE 
                            WHEN cr.report_date = CURRENT_DATE 
                            THEN (SELECT COUNT(*) FROM crm_lead cl 
                                  WHERE (cr.user_id IS NULL AND cl.user_id IS NULL) OR (cr.user_id IS NOT NULL AND cl.user_id = cr.user_id))
                            ELSE 0 
                        END AS lead_count,
                        CASE 
                            WHEN cr.report_date = CURRENT_DATE 
                            THEN (SELECT COUNT(*) FROM crm_lead cl 
                                  WHERE ((cr.user_id IS NULL AND cl.user_id IS NULL) OR (cr.user_id IS NOT NULL AND cl.user_id = cr.user_id)) 
                                  AND cl.type = 'opportunity')
                            ELSE 0 
                        END AS opportunity_count,
                        CASE 
                            WHEN cr.report_date = CURRENT_DATE 
                            THEN (SELECT COUNT(*) FROM crm_lead cl 
                                  LEFT JOIN crm_stage cs ON cs.id = cl.stage_id 
                                  WHERE ((cr.user_id IS NULL AND cl.user_id IS NULL) OR (cr.user_id IS NOT NULL AND cl.user_id = cr.user_id)) 
                                  AND cl.type = 'opportunity' AND cs.is_won = TRUE)
                            ELSE 0 
                        END AS won_count
                    FROM combined_raw cr
                    GROUP BY cr.user_id, cr.report_date
                ),
                existing_user_dates AS (
                    SELECT DISTINCT user_id, report_date FROM grouped
                ),
                missing_user_dates AS (
                    SELECT user_id, report_date FROM user_dates
                    EXCEPT
                    SELECT user_id, report_date FROM existing_user_dates
                ),
                dummy_rows AS (
                    SELECT
                        m.user_id,
                        m.report_date,
                        NULL::integer AS lead_id,
                        NULL::integer AS partner_id,
                        NULL::integer AS team_id,
                        0 AS planned_visits,
                        0::float AS planned_duration,
                        0 AS actual_visits,
                        0::float AS actual_duration,
                        0 AS visit_variance,
                        0::float AS duration_variance,
                        0 AS visit_completion_rate,
                        CASE 
                            WHEN m.report_date = CURRENT_DATE 
                            THEN (SELECT COUNT(*) FROM crm_lead cl 
                                  WHERE (m.user_id IS NULL AND cl.user_id IS NULL) OR (m.user_id IS NOT NULL AND cl.user_id = m.user_id))
                            ELSE 0 
                        END AS lead_count,
                        CASE 
                            WHEN m.report_date = CURRENT_DATE 
                            THEN (SELECT COUNT(*) FROM crm_lead cl 
                                  WHERE ((m.user_id IS NULL AND cl.user_id IS NULL) OR (m.user_id IS NOT NULL AND cl.user_id = m.user_id)) 
                                  AND cl.type = 'opportunity')
                            ELSE 0 
                        END AS opportunity_count,
                        CASE 
                            WHEN m.report_date = CURRENT_DATE 
                            THEN (SELECT COUNT(*) FROM crm_lead cl 
                                  LEFT JOIN crm_stage cs ON cs.id = cl.stage_id 
                                  WHERE ((m.user_id IS NULL AND cl.user_id IS NULL) OR (m.user_id IS NOT NULL AND cl.user_id = m.user_id)) 
                                  AND cl.type = 'opportunity' AND cs.is_won = TRUE)
                            ELSE 0 
                        END AS won_count
                    FROM missing_user_dates m
                ),
                all_rows AS (
                    SELECT * FROM grouped
                    UNION ALL
                    SELECT * FROM dummy_rows
                )
                SELECT
                    ROW_NUMBER() OVER () AS id,
                    user_id,
                    report_date,
                    lead_id,
                    partner_id,
                    team_id,
                    planned_visits,
                    planned_duration,
                    actual_visits,
                    actual_duration,
                    visit_variance,
                    duration_variance,
                    visit_completion_rate,
                    lead_count,
                    opportunity_count,
                    won_count,
                    CASE
                        WHEN actual_lead_count > 0
                        THEN ROUND((actual_opportunity_count::numeric / actual_lead_count::numeric) * 100, 2)
                        ELSE 0
                    END AS lead_to_opportunity_rate,
                    CASE
                        WHEN actual_opportunity_count > 0
                        THEN ROUND((actual_won_count::numeric / actual_opportunity_count::numeric) * 100, 2)
                        ELSE 0
                    END AS opportunity_to_won_rate
                FROM (
                    SELECT
                        ar.*,
                        (SELECT COUNT(*) FROM crm_lead cl 
                         WHERE (ar.user_id IS NULL AND cl.user_id IS NULL) OR (ar.user_id IS NOT NULL AND cl.user_id = ar.user_id)) AS actual_lead_count,
                        (SELECT COUNT(*) FROM crm_lead cl 
                         WHERE ((ar.user_id IS NULL AND cl.user_id IS NULL) OR (ar.user_id IS NOT NULL AND cl.user_id = ar.user_id)) 
                         AND cl.type = 'opportunity') AS actual_opportunity_count,
                        (SELECT COUNT(*) FROM crm_lead cl 
                         LEFT JOIN crm_stage cs ON cs.id = cl.stage_id 
                         WHERE ((ar.user_id IS NULL AND cl.user_id IS NULL) OR (ar.user_id IS NOT NULL AND cl.user_id = ar.user_id)) 
                         AND cl.type = 'opportunity' AND cs.is_won = TRUE) AS actual_won_count
                    FROM all_rows ar
                ) AS ar_with_actuals
            )
        """ % self._table)