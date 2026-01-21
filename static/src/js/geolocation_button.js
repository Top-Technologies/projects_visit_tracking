/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, xml } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export class VisitGeolocationButton extends Component {
    static template = "sales_visit_tracking.VisitGeolocationButton";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
    }

    async onClickCheckIn() {
        if (!this.isMobileDevice()) {
            this.notification.add("Please use a mobile device to check in.", {
                type: "danger",
            });
            return;
        }

        if (!navigator.geolocation) {
            this.notification.add("Geolocation is not supported by your browser.", {
                type: "danger",
            });
            return;
        }

        navigator.geolocation.getCurrentPosition(
            (position) => this.onPositionSuccess(position),
            (error) => this.onPositionError(error),
            { enableHighAccuracy: true }
        );
    }

    isMobileDevice() {
        // Simple regex check for mobile user agents
        const ua = navigator.userAgent;
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ua);
    }

    async onPositionSuccess(position) {
        const { latitude, longitude } = position.coords;
        const device_info = navigator.userAgent;

        try {
            await this.props.record.update({
                latitude: latitude,
                longitude: longitude,
                device_info: device_info,
                visit_date: luxon.DateTime.now(),
                state: 'done'
            });
            
            await this.props.record.save();
            
            this.notification.add("Checked in successfully!", {
                type: "success",
            });
        } catch (error) {
            this.notification.add("Error during check-in: " + error.message, {
                type: "danger",
            });
        }
    }

    onPositionError(error) {
        let msg = "Error getting location.";
        switch (error.code) {
            case error.PERMISSION_DENIED:
                msg = "User denied the request for Geolocation.";
                break;
            case error.POSITION_UNAVAILABLE:
                msg = "Location information is unavailable.";
                break;
            case error.TIMEOUT:
                msg = "The request to get user location timed out.";
                break;
            case error.UNKNOWN_ERROR:
                msg = "An unknown error occurred.";
                break;
        }
        this.notification.add(msg, {
            type: "danger",
        });
    }
}

registry.category("view_widgets").add("visit_geolocation_button", {
    component: VisitGeolocationButton,
});
