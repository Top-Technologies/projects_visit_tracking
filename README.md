# Project Visit Tracking

Track project visits with geolocation on project module. This module provides a robust way to monitor field activities, visualize visit routes, and manage visit records with proper access control.

## Features

### 📍 Visit Check-in
*   **Mobile Only Restriction**: Check-ins are strictly restricted to mobile devices (detected via User Agent) to ensure records are made on-site.
*   **Geolocation Capture**: Automatically captures latitude, longitude, and device info.
*   **Reverse Geocoding**: Automatically fetches the physical address of the check-in location using server-side Nominatim integration.

### 🗺️ Interactive Dashboard
*   **Visit Map Dashboard**: A dedicated view using Leaflet.js to visualize visits on an interactive map.
*   **Route Visualization**: Connects visits for a specific salesperson on a specific day to show their route.
*   **Filtering**: Filter visits by Salesperson and Date to analyze field coverage.

### 🔐 Access Control & Security
*   **Record Rules**:
    *   **Team Member**: Can only see and manage their own visit records.
    *   **Project Managers**: Have full visibility into all visits across the team.
*   **Menu Visibility**: Sensitive menus like "Cancellation Requests" and "Reports" are restricted to managers.

### 🔄 Cancellation Workflow
*   **Requests**: Team member can request the cancellation of a visit if it was recorded in error.
*   **Approval**: Project Managers can review, approve, or reject cancellation requests.

## Dependencies

This module depends on the following standard Odoo modules:
*   `base`
*   `web`
*   `project`


## Technical Details

*   **Version**: 19.0.1.0.0
*   **License**: LGPL-3
*   **External Libraries**: Uses Leaflet.js (loaded dynamically) for map rendering.
*   **API**: Uses Nominatim (OpenStreetMap) for reverse geocoding.
