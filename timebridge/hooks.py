app_name = "timebridge"
app_title = "TimeBridge"
app_publisher = "UPGO"
app_description = "Connect biometric devices with Frappe ERP for attendance synchronization."
app_email = "email@example.com"
app_license = "mit"

# ADMS push receiver
# ------------------
# Devices that push (eSSL AIFace, newer ZKTeco) have their paths hardcoded in
# firmware — they call /iclock/cdata, never /api/method/... A page_renderer is
# how an app claims arbitrary website paths, and it gives us the raw POST body
# and a text/plain response, neither of which website_route_rules can provide.
page_renderer = [
	"timebridge.timebridge.adms.renderer.ADMSRenderer",
]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "timebridge",
# 		"logo": "/assets/timebridge/logo.png",
# 		"title": "TimeBridge",
# 		"route": "/timebridge",
# 		"has_permission": "timebridge.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/timebridge/css/timebridge.css"
# app_include_js = "/assets/timebridge/js/timebridge.js"

# include js, css files in header of web template
# web_include_css = "/assets/timebridge/css/timebridge.css"
# web_include_js = "/assets/timebridge/js/timebridge.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "timebridge/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "timebridge/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "timebridge.utils.jinja_methods",
# 	"filters": "timebridge.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "timebridge.install.before_install"
# after_install = "timebridge.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "timebridge.uninstall.before_uninstall"
# after_uninstall = "timebridge.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "timebridge.utils.before_app_install"
# after_app_install = "timebridge.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "timebridge.utils.before_app_uninstall"
# after_app_uninstall = "timebridge.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "timebridge.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# Keep attendance current without anyone pressing a button.
#
# Punches arrive on their own over ADMS, but they are only raw timestamps —
# this is what turns them into first_in / last_out / hours. A short trailing
# window rather than the whole history: today's row changes every time someone
# punches out, and yesterday's can still change if the device delivers late.
scheduler_events = {
	"cron": {
		"*/15 * * * *": [
			"timebridge.timebridge.services.attendance_sync.rebuild_recent"
		],
		# More often than attendance: a device that has stopped sending should
		# show as Disconnected quickly, not up to fifteen minutes later.
		"*/2 * * * *": [
			"timebridge.timebridge.services.attendance_sync.refresh_push_device_status"
		]
	}
}

# scheduler_events = {
# 	"all": [
# 		"timebridge.tasks.all"
# 	],
# 	"daily": [
# 		"timebridge.tasks.daily"
# 	],
# 	"hourly": [
# 		"timebridge.tasks.hourly"
# 	],
# 	"weekly": [
# 		"timebridge.tasks.weekly"
# 	],
# 	"monthly": [
# 		"timebridge.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "timebridge.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "timebridge.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "timebridge.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
before_request = ["timebridge.timebridge.query_compat.remap_old_employee_name"]
# after_request = ["timebridge.utils.after_request"]

# Job Events
# ----------
# before_job = ["timebridge.utils.before_job"]
# after_job = ["timebridge.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"timebridge.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

