/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, xml, onMounted, onWillUnmount, useState } from "@odoo/owl";

export class VisitMapDashboard extends Component {
    static template = "sales_visit_tracking.VisitMapDashboard";
    static props = {
        action: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            visits: [],
            salespeople: [],
            selectedUser: null,
            selectedDate: this.getTodayString(),
            isManager: false,
            loading: true,
        });
        this.map = null;
        this.visitMarkers = [];
        this.plannedMarkers = [];
        this.plannedRouteLine = null;
        this.actualRouteLine = null;

        onMounted(() => this.initMap());
        onWillUnmount(() => this.destroyMap());

        this.onUserChange = this.onUserChange.bind(this);
        this.onDateChange = this.onDateChange.bind(this);
        this.onRefresh = this.onRefresh.bind(this);
    }

    getTodayString() {
        const today = new Date();
        return today.toISOString().split('T')[0];
    }

    async initMap() {
        // Load Leaflet CSS dynamically
        if (!document.querySelector('link[href*="leaflet.css"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
            document.head.appendChild(link);
        }

        // Load Leaflet JS dynamically
        if (!window.L) {
            await new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
                script.onload = resolve;
                script.onerror = reject;
                document.head.appendChild(script);
            });
        }

        // Wait for container to be ready
        await new Promise(resolve => setTimeout(resolve, 100));

        const mapContainer = document.getElementById('visit-map');
        if (!mapContainer || !window.L) return;

        // Initialize map centered on a default location
        this.map = L.map('visit-map').setView([0, 0], 2);

        // Ensure deterministic stacking when markers overlap:
        // planned route (stops/lines) below, visits above.
        this.map.createPane('plannedPane');
        this.map.getPane('plannedPane').style.zIndex = 350;
        this.map.createPane('visitPane');
        this.map.getPane('visitPane').style.zIndex = 450;

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: ' OpenStreetMap contributors'
        }).addTo(this.map);

        await this.loadUserRole();
        if (this.state.isManager) {
            await this.loadSalespeople();
        } else {
            const me = await this.orm.call("visit.route", "get_current_user", []);
            if (me?.id) {
                this.state.selectedUser = String(me.id);
            }
        }
        await this.loadAll();
    }

    async loadAll() {
        await this.loadVisits();
        await this.loadPlannedRouteOverlay();
        const selectedUserId = this.state.selectedUser ? parseInt(this.state.selectedUser) : false;
        await this.loadActualRouteTaken(selectedUserId);
    }

    async loadPlannedRouteOverlay() {
        if (!this.state.selectedUser) return;
        try {
            const data = await this.orm.call(
                "visit.route",
                "get_route_map_data",
                [],
                {
                    user_id: parseInt(this.state.selectedUser),
                    route_date: this.state.selectedDate,
                }
            );
            const stops = data?.stops || [];
            this.renderRouteStops(stops, { fitBounds: false });
        } catch (e) {
            // no planned route found or access denied - ignore silently
        }
    }

    destroyMap() {
        if (this.map) {
            this.map.remove();
            this.map = null;
        }
    }

    async loadActualRouteTaken(userId) {
        try {
            if (!userId) {
                return;
            }
            const domain = [["state", "in", ["done", "checked_out"]]];

            if (userId) {
                domain.push(["user_id", "=", userId]);
            }

            if (this.state.selectedDate) {
                const startDate = this.state.selectedDate + " 00:00:00";
                const endDate = this.state.selectedDate + " 23:59:59";
                domain.push(["visit_date", ">=", startDate]);
                domain.push(["visit_date", "<=", endDate]);
            }

            const visits = await this.orm.searchRead(
                "visit.tracker",
                domain,
                ["id", "visit_date", "latitude", "longitude"],
                { order: "visit_date asc" }
            );

            const coords = (visits || [])
                .filter(v => (v.latitude || v.latitude === 0) && (v.longitude || v.longitude === 0))
                .map(v => [v.latitude, v.longitude]);

            if (coords.length < 2 || !this.map || !window.L) {
                return;
            }

            this.actualRouteLine = L.polyline(coords, {
                color: '#e74c3c',
                weight: 4,
                opacity: 0.75,
            }).addTo(this.map);

            const bounds = coords;
            if (bounds.length > 0) {
                this.map.fitBounds(bounds, { padding: [50, 50] });
            }
        } catch (e) {
            console.warn("Failed to load actual route taken:", e);
        }
    }

    async loadUserRole() {
        try {
            this.state.isManager = await this.orm.call("visit.route", "is_sales_manager", []);
        } catch (e) {
            this.state.isManager = false;
        }
    }

    async loadSalespeople() {
        try {
            const users = await this.orm.searchRead(
                "res.users",
                [["share", "=", false]],
                ["id", "name"],
                { limit: 100 }
            );
            this.state.salespeople = users;
        } catch (e) {
            console.error("Failed to load salespeople:", e);
        }
    }

    async loadVisits() {
        this.state.loading = true;
        this.state.visits = [];
        this.clearMap();

        try {
            const domain = [["state", "in", ["done", "checked_out"]]];

            if (this.state.selectedUser) {
                domain.push(["user_id", "=", parseInt(this.state.selectedUser)]);
            }

            if (this.state.selectedDate) {
                const startDate = this.state.selectedDate + " 00:00:00";
                const endDate = this.state.selectedDate + " 23:59:59";
                domain.push(["visit_date", ">=", startDate]);
                domain.push(["visit_date", "<=", endDate]);
            }

            // Fetch visits
            const options = { order: "visit_date desc" };
            if (!this.state.selectedUser) {
                options.limit = 2000;
            }

            let visits = await this.orm.searchRead(
                "visit.tracker",
                domain,
                ["id", "user_id", "partner_id", "visit_date", "latitude", "longitude", "location_address", "notes"],
                options
            );

            if (!this.state.selectedUser) {
                const latestByUser = new Map();
                for (const v of visits) {
                    const uid = v.user_id && v.user_id[0];
                    if (!uid) continue;
                    if (!latestByUser.has(uid)) {
                        latestByUser.set(uid, v);
                    }
                }
                visits = Array.from(latestByUser.values());
            }

            // If user selected, we usually want chronological order for the route
            if (this.state.selectedUser) {
                visits.sort((a, b) => new Date(a.visit_date) - new Date(b.visit_date));
            }

            this.state.visits = visits;
            this.renderMarkers(visits);
        } catch (error) {
            console.error("Failed to load visits:", error);
            this.notification.add("Failed to load visits", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    clearMap() {
        this.visitMarkers.forEach(marker => marker.remove());
        this.visitMarkers = [];
        this.plannedMarkers.forEach(marker => marker.remove());
        this.plannedMarkers = [];

        if (this.plannedRouteLine) {
            this.plannedRouteLine.remove();
            this.plannedRouteLine = null;
        }
        if (this.actualRouteLine) {
            this.actualRouteLine.remove();
            this.actualRouteLine = null;
        }
    }

    renderRouteStops(stops, opts = {}) {
        if (!this.map || !window.L) return;
        const { fitBounds = true } = opts;
        const bounds = [];
        const routeCoords = [];

        for (const stop of stops) {
            if (!((stop.latitude || stop.latitude === 0) && (stop.longitude || stop.longitude === 0))) {
                continue;
            }

            const latlng = [stop.latitude, stop.longitude];
            bounds.push(latlng);
            routeCoords.push(latlng);

            const pinType = stop.pin_type || 'missing';
            const className = pinType === 'known'
                ? 'visit-marker known'
                : pinType === 'manual_exact'
                    ? 'visit-marker manual_exact'
                    : pinType === 'manual_approx'
                        ? 'visit-marker manual_approx'
                        : 'visit-marker missing';

            const icon = L.divIcon({
                className,
                html: `<div class="marker-dot">${stop.sequence || ''}</div>`,
                iconSize: [34, 34],
                iconAnchor: [14, 14],
            });

            const marker = L.marker(latlng, { icon, pane: 'plannedPane' }).addTo(this.map);
            marker.setZIndexOffset(100);

            const popupContent = `
                <div style="min-width: 220px;">
                    <strong>${stop.lead_name || ''}</strong><br/>
                    ${stop.partner_name ? `<small>Customer: ${stop.partner_name}</small><br/>` : ''}
                    ${stop.address ? `<small> ${String(stop.address).substring(0, 100)}...</small><br/>` : ''}
                    <small>Pin type: ${pinType}</small>
                </div>
            `;
            marker.bindPopup(popupContent);
            this.plannedMarkers.push(marker);
        }

        if (routeCoords.length > 1) {
            this.plannedRouteLine = L.polyline(routeCoords, {
                pane: 'plannedPane',
                color: '#3498db',
                weight: 3,
                opacity: 0.7,
                dashArray: '10, 10'
            }).addTo(this.map);
        }

        if (fitBounds && bounds.length > 0) {
            this.map.fitBounds(bounds, { padding: [50, 50] });
        }
    }

    renderMarkers(visits) {
        if (!this.map || !window.L) return;

        const validVisits = visits.filter(v => (v.latitude || v.latitude === 0) && (v.longitude || v.longitude === 0));
        if (validVisits.length === 0) return;

        const bounds = [];
        const routeCoords = [];

        // Group by user for different colors
        const userColors = {};
        const colors = ['#e74c3c', '#3498db', '#2ecc71', '#9b59b6', '#f39c12', '#1abc9c'];
        let colorIndex = 0;

        validVisits.forEach((visit, idx) => {
            const userId = visit.user_id[0];
            if (!userColors[userId]) {
                userColors[userId] = colors[colorIndex % colors.length];
                colorIndex++;
            }
            const color = userColors[userId];

            const latlng = [visit.latitude, visit.longitude];
            bounds.push(latlng);
            routeCoords.push(latlng);

            // Create custom icon with number
            const icon = L.divIcon({
                className: 'visit-marker',
                html: `<div style="background-color: ${color}; color: white; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 12px; border: 2px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.3);">${idx + 1}</div>`,
                iconSize: [28, 28],
                iconAnchor: [14, 14],
            });

            const marker = L.marker(latlng, { icon }).addTo(this.map);

            // Create popup content
            const visitDate = new Date(visit.visit_date).toLocaleTimeString();
            const popupContent = `
                <div style="min-width: 200px;">
                    <strong>${visit.partner_id[1]}</strong><br/>
                    <small>Salesperson: ${visit.user_id[1]}</small><br/>
                    <small>Time: ${visitDate}</small><br/>
                    ${visit.location_address ? `<small> ${visit.location_address.substring(0, 100)}...</small><br/>` : ''}
                    ${visit.notes ? `<small> ${visit.notes}</small>` : ''}
                </div>
            `;
            marker.bindPopup(popupContent);

            this.visitMarkers.push(marker);
        });

        // Draw route line if showing single user
        // if (this.state.selectedUser && routeCoords.length > 1) {
        //     this.actualRouteLine = L.polyline(routeCoords, {
        //         pane: 'visitPane',
        //         color: userColors[parseInt(this.state.selectedUser)] || '#3498db',
        //         weight: 3,
        //         opacity: 0.7,
        //         dashArray: '10, 10'
        //     }).addTo(this.map);
        // }

        // Fit map to bounds
        if (bounds.length > 0) {
            this.map.fitBounds(bounds, { padding: [50, 50] });
        }
    }

    onUserChange(ev) {
        this.state.selectedUser = ev.target.value || null;
        this.loadAll();
    }

    onDateChange(ev) {
        this.state.selectedDate = ev.target.value;
        this.loadAll();
    }

    onRefresh() {
        this.loadAll();
    }
}

registry.category("actions").add("sales_visit_tracking.visit_map_dashboard", VisitMapDashboard);
