from pathlib import Path

import frappe
from weasyprint import HTML


@frappe.whitelist()
def download_setup_guide():
    guide = Path(__file__).with_name("timebridge_setup.html").read_text(encoding="utf-8")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Timebridge Setup</title>
<style>
@page {{ size: A4; margin: 18mm; }}
body {{ font-family: sans-serif; font-size: 13px; line-height: 1.45; color: #1f272e; }}
h1 {{ font-size: 22px; margin: 0 0 12px; }}
h4 {{ font-size: 15px; margin: 22px 0 8px; }}
ol, ul {{ padding-left: 22px; }}
li {{ margin: 4px 0; }}
code {{ font-size: 12px; }}
</style>
</head>
<body>
<h1>Timebridge Setup</h1>
{guide}
</body>
</html>"""

    frappe.local.response.filename = "Timebridge-Setup.pdf"
    frappe.local.response.filecontent = HTML(string=html).write_pdf()
    frappe.local.response.type = "pdf"
