// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.listview_settings["TimeBridge Attendance"] = {

    /*
     * Drop the "TimeBridge Employee Name" box from the filter row.
     *
     * It is not there because anyone asked for it: Frappe adds the DocType's
     * title_field as a standard filter automatically —
     *
     *     df.fieldname === title_field || (df.in_standard_filter && ...)
     *                                     (base_list.js, make_standard_filters)
     *
     * — and this DocType's title_field is employee_name. So setting
     * in_standard_filter to 0 has no effect at all; the only supported lever
     * is to remove the control after the row is built.
     *
     * The alternative, changing title_field, would be worse: link dropdowns
     * would go back to showing ATT-105960 instead of the person's name.
     *
     * The TimeBridge Employee filter stays, and searches by name anyway now that links
     * show their title — so nothing is lost by removing the duplicate.
     */
    onload(listview) {
        remove_standard_filter(listview, "employee_name");
    },

    refresh(listview) {
        // The filter row is rebuilt on some navigations, so this runs again
        // rather than only once at load.
        remove_standard_filter(listview, "employee_name");
    }

};


function remove_standard_filter(listview, fieldname) {

    const field = listview.page.fields_dict && listview.page.fields_dict[fieldname];

    if (!field) {
        return;
    }

    if (field.$wrapper) {
        field.$wrapper.remove();
    }

    // Also drop it from fields_dict, or get_standard_filters() keeps reading a
    // control that is no longer on the page.
    delete listview.page.fields_dict[fieldname];
}
