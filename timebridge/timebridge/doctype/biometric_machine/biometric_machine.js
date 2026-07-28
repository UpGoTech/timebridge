// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Biometric Machine", {
// 	refresh(frm) {
		
// 	},
// });

frappe.ui.form.on("Biometric Machine", {

    refresh(frm) {

        frm.add_custom_button("Test Connection", function(){

            frappe.call({

                method: "timebridge.api.test_connection",

                args: {
                    machine_id: frm.doc.name
                },

                callback: function(r){

                    console.log(r.message);

                    if(r.message.status === "success"){

                        frappe.msgprint({
                            title: "Success",
                            message: r.message.message,
                            indicator: "green"
                        });

                    }else{

                        frappe.msgprint({
                            title: "Failed",
                            message: r.message.message,
                            indicator: "red"
                        });

                    }

                }

            });

        });

    }

});