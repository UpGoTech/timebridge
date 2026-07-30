// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Biometric Machine", {
// 	refresh(frm) {
		
// 	},
// });

const DEVICE_INFO_EVENT = "timebridge_device_info";

frappe.ui.form.on("Biometric Machine", {

    refresh(frm) {

        listen_for_device_info(frm);

        frm.add_custom_button("Test Connection", function(){

            if(frm.is_new()){

                frappe.msgprint({
                    title: "Not Saved",
                    message: "Save the machine before testing the connection.",
                    indicator: "orange"
                });

                return;

            }

            frappe.call({

                method: "timebridge.timebridge.api.get_device_info",

                args: {
                    machine_id: frm.doc.name
                },

                // The endpoint only queues the read, so this callback
                // fires long before the device answers. The outcome
                // arrives on DEVICE_INFO_EVENT instead.
                callback: function(r){

                    if(!r.message){
                        return;
                    }

                    frappe.show_alert({
                        message: r.message.message,
                        indicator: "blue"
                    });

                }

            });

        });

    }

});


function listen_for_device_info(frm){

    // refresh() runs on every form render, but frappe.realtime.on
    // registers globally — without this guard the handler stacks up
    // and one result would raise several dialogs.
    if(frm.__device_info_bound){
        return;
    }

    frm.__device_info_bound = true;

    frappe.realtime.on(DEVICE_INFO_EVENT, function(data){

        // The listener outlives navigation to another machine, so
        // ignore anything meant for a document we are not showing.
        if(!data || data.machine_id !== frm.doc.name){
            return;
        }

        if(data.status === "success"){

            frappe.show_alert({
                message: data.message,
                indicator: "green"
            });

            frm.reload_doc();

        }else{

            frappe.msgprint({
                title: "Connection Failed",
                message: data.message,
                indicator: "red"
            });

        }

    });

}