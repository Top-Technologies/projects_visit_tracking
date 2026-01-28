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
            loading: true,
        });
        this.map = null;
        this.markers = [];
        this.routeLine = null;

        onMounted(() => this.initMap());
        onWillUnmount(() => this.destroyMap());
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

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(this.map);

        // Load salespeople and visits
        await this.loadSalespeople();
        await this.loadVisits();
    }

    destroyMap() {
        if (this.map) {
            this.map.remove();
            this.map = null;
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
        this.clearMap();

        try {
            const domain = [["state", "=", "done"]];

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
            let visits = await this.orm.searchRead(
                "visit.tracker",
                domain,
                ["id", "user_id", "partner_id", "visit_date", "latitude", "longitude", "location_address", "notes"],
                { order: "visit_date desc" } // Order by desc to get latest first
            );

            // If no user is selected, filter to keep only the latest visit per user
            if (!this.state.selectedUser && visits.length > 0) {
                const latestVisits = [];
                const seenUsers = new Set();

                for (const visit of visits) {
                    const userId = visit.user_id[0];
                    if (!seenUsers.has(userId)) {
                        seenUsers.add(userId);
                        latestVisits.push(visit);
                    }
                }
                visits = latestVisits;

                // Re-sort by ID or name if needed, or keep by date (latest first)
            } else {
                // If user selected, we usually want chronological order for the route
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
        this.markers.forEach(marker => marker.remove());
        this.markers = [];
        if (this.routeLine) {
            this.routeLine.remove();
            this.routeLine = null;
        }
    }

    renderMarkers(visits) {
        if (!this.map || !window.L) return;

        const validVisits = visits.filter(v => v.latitude && v.longitude);
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
                    ${visit.location_address ? `<small>📍 ${visit.location_address.substring(0, 100)}...</small><br/>` : ''}
                    ${visit.notes ? `<small>📝 ${visit.notes}</small>` : ''}
                </div>
            `;
            marker.bindPopup(popupContent);

            this.markers.push(marker);
        });

        // Draw route line if showing single user
        if (this.state.selectedUser && routeCoords.length > 1) {
            this.routeLine = L.polyline(routeCoords, {
                color: userColors[parseInt(this.state.selectedUser)] || '#3498db',
                weight: 3,
                opacity: 0.7,
                dashArray: '10, 10'
            }).addTo(this.map);
        }

        // Fit map to bounds
        if (bounds.length > 0) {
            this.map.fitBounds(bounds, { padding: [50, 50] });
        }
    }

    onUserChange(ev) {
        this.state.selectedUser = ev.target.value || null;
        this.loadVisits();
    }

    onDateChange(ev) {
        this.state.selectedDate = ev.target.value;
        this.loadVisits();
    }

    onRefresh() {
        this.loadVisits();
    }
}

registry.category("actions").add("sales_visit_tracking.visit_map_dashboard", VisitMapDashboard);
