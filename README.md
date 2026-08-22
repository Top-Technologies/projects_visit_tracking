# Projects Visit Tracking & Planning

A mobile-friendly Odoo 19 module for planning project site visits, performing GPS check-in/check-out on mobile devices, and analyzing planned vs. actual hours spent on site.

## Key Features

### 📅 Project Visit Planning
* **Flexible Planning Modes**:
  * **Full Day(s)**: Automatically calculates planned hours at 8 hours/day based on date range (e.g., Aug 1 to Aug 5 = 5 days × 8h = 40 hours).
  * **Custom Hours**: Allows direct input of specific hours planned for the visit.
* **Approval Workflow & Auto-Notifications**:
  * Employees draft visit plans and submit them for approval (`Draft` → `Approval Requested` → `Approved`).
  * Requesting approval automatically notifies all users with **Project Administrator** access rights (`project.group_project_manager`) via Chatter and schedules To-Do activities in their top-bar activity menu.
  * Project Administrators can approve, reject, or reset plans.

### 📍 Multi-Device GPS Check-in & Check-out
* **Desktop, Laptop & Mobile Support**: Check-in and check-out are supported across all devices (laptops, PCs, tablets, mobile browsers) using standard browser geolocation.
* **One-Click Check-in on Approved Plan**: Employees open their approved plan and click "Check In at Site" or check in directly from the Project form header.
* **GPS & Timestamp Capture**: Automatically records check-in and check-out time, GPS coordinates, device info, and reverse-geocodes physical address.
* **Proximity & Duration Safeguard**: Automatically calculates time spent and detects check-outs beyond site tolerance.

### ⏱️ Planned vs. Actual Time Tracking
* **Real-Time Metrics on Plan**:
  * Total Planned Hours vs. Total Actual Hours Spent.
  * Remaining / Variance Hours.
  * Visual Progress bar & Completion percentage.
  * Detailed session history of all check-ins for the plan.
* **Smart Project Integration**:
  * Smart buttons on Project form showing Visit Plans and Check-in count with total site hours.
  * Direct check-in from Project form automatically links to today's approved plan.

### 🗺️ Live Interactive Map & Reporting
* **Live Map Dashboard**: Visualizes team members' site locations, planned project stops, and paths taken using Leaflet.js.
* **Planned vs. Actual Analysis**:
  * Pivot, Graph, and List views comparing planned visit hours against actual check-in duration.
  * Filterable by team member, project, day, week, or month.

## Security & Access Control
* **Team Members (`project.group_project_user`)**: Create and manage own visit plans and check-ins.
* **Project Managers (`project.group_project_manager`)**: Full access to review, approve/reject plans, view all team visits, manage cancellation requests, and access analysis reports.
