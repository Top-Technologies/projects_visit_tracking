# Sales Visit Tracking

Track salesperson visits with geolocation on CRM leads. This module provides a robust way to monitor field activities, visualize visit routes, and manage visit records with proper access control.

## Features

### 📍 Visit Check-in
*   **CRM Lead Integration**: A "Check In" button is available on CRM Lead/Opportunity forms.
*   **Mobile Only Restriction**: Check-ins are strictly restricted to mobile devices (detected via User Agent) to ensure records are made on-site.
*   **Geolocation Capture**: Automatically captures latitude, longitude, and device info.
*   **Reverse Geocoding**: Automatically fetches the physical address of the check-in location using server-side Nominatim integration.

### 🗺️ Interactive Dashboard
*   **Visit Map Dashboard**: A dedicated view using Leaflet.js to visualize visits on an interactive map.
*   **Route Visualization**: Connects visits for a specific salesperson on a specific day to show their route.
*   **Filtering**: Filter visits by Salesperson and Date to analyze field coverage.

### 🔐 Access Control & Security
*   **Record Rules**:
    *   **Salespersons**: Can only see and manage their own visit records.
    *   **Sales Managers**: Have full visibility into all visits across the team.
*   **Menu Visibility**: Sensitive menus like "Cancellation Requests" and "Reports" are restricted to managers.

### 🔄 Cancellation Workflow
*   **Requests**: Salespersons can request the cancellation of a visit if it was recorded in error.
*   **Approval**: Sales Managers can review, approve, or reject cancellation requests.

### 📊 Reporting & Analysis
*   **Pivot & Graph Views**: Analyze visit data with standard Odoo reporting tools.
*   **Grouping**: Group by Salesperson, Customer, or Date to gain insights into field performance.

## Dependencies

This module depends on the following standard Odoo modules:
*   `base`
*   `web`
*   `crm`
*   `sales_team`

## Technical Details

*   **Version**: 18.0.1.2.0
*   **License**: LGPL-3
*   **External Libraries**: Uses Leaflet.js (loaded dynamically) for map rendering.
*   **API**: Uses Nominatim (OpenStreetMap) for reverse geocoding.
