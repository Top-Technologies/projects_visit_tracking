{
    'name': 'Sales Visit Tracking',
    'version': '18.0.1.2.0',
    'category': 'CRM',
    'summary': 'Track salesperson visits with geolocation on CRM leads',
    'description': """
        This module allows tracking of salesperson visits to leads/opportunities.
        Features:
        - Check-in button on CRM lead form with geolocation capture
        - Interactive map dashboard with route visualization
        - Pivot and graph views for visit analysis
        - Filter by salesperson, date, and lead
    """,
    'author': 'Top-tech',
    'depends': ['base', 'web', 'crm', 'sales_team'],
    'data': [
        'security/ir.model.access.csv',
        'views/visit_tracker_views.xml',
        'views/crm_lead_views.xml',
        'views/visit_dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sales_visit_tracking/static/src/css/visit_map.css',
            'sales_visit_tracking/static/src/js/geolocation_button.js',
            'sales_visit_tracking/static/src/js/visit_map.js',
            'sales_visit_tracking/static/src/xml/geolocation_button.xml',
            'sales_visit_tracking/static/src/xml/visit_map.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
