# kaisight

Interactive dashboards and saved reports for any Odoo model, built on the standard ORM (`search_read`, `read_group`, `search_count`).

**Version:** 19.0.1.0.4  
**License:** LGPL-3  
**Author:** [Kaiddons](https://kaizened.in)

## Features

- **Dashboards** — configurable grid of widgets (KPI, chart, record list)
- **Saved reports** — reusable window actions with domain filters for any installed model
- **Sharing** — dashboards and reports can be private or shared with all internal users
- **Extensible** — other addons can ship dashboards/widgets via XML data or Python API

## Requirements

- Odoo **19.0**
- Dependencies: `base`, `web`

## Installation

1. Clone this repository into your Odoo addons path:

   ```bash
   git clone https://github.com/iamzic/kaisight.git
   ```

2. Update the apps list and install **kaisight** from the Odoo Apps menu.

3. Open **kaisight → Dashboard** to view the sample dashboard (demo data is loaded on install).

## Usage

| Menu | Description |
|------|-------------|
| kaisight → Dashboard | Main interactive dashboard view |
| kaisight → Configuration → Dashboards | Create and edit dashboards and widgets |
| kaisight → Configuration → Saved reports | Manage saved report shortcuts |

### Widget types

| Type | Description |
|------|-------------|
| **KPI / Count** | Single metric (count, sum, or average) with optional drill-down |
| **Chart** | Bar, line, pie, or doughnut chart via `read_group` |
| **Record list** | Filtered list preview with click-through to records |

## Extending from another addon

Register widgets on a dashboard defined in your module:

```python
self.env["kai.view.dashboard"].register_widgets_from_addon(
    "my_addon.dashboard_sales",
    [
        {
            "name": "Open quotations",
            "widget_type": "kpi",
            "model_id": self.env.ref("sale.model_sale_order").id,
            "domain": "[('state', '=', 'draft')]",
            "aggregate": "count",
            "icon": "fa-file-text-o",
        },
    ],
)
```

## Development

After changing JavaScript or SCSS assets, upgrade the module and hard-refresh the browser:

```bash
./odoo-bin -u kaisight -d your_database
```

## Contributing

Issues and pull requests are welcome on GitHub.

## Troubleshooting: `No module named 'odoo.addons.kAISight'`

If the addon folder is `kaisight` but the database was installed when the module was named `kAISight`, Odoo still tries to import the old name and the registry fails to load.

1. Keep the folder named exactly `kaisight` (lowercase).
2. Rename the module in PostgreSQL (replace `odoonew` with your DB name):

```bash
docker compose exec -T odoo19-db psql -U odoo -d odoonew -c "
UPDATE ir_module_module SET name = 'kaisight' WHERE name = 'kAISight';
UPDATE ir_module_module_dependency SET name = 'kaisight' WHERE name = 'kAISight';
UPDATE ir_model_data SET module = 'kaisight' WHERE module = 'kAISight';
"
```

Or apply the included script: `rename_module_to_kaisight.sql`.

3. Restart Odoo, then upgrade **kaisight** from Apps (or `-u kaisight`).

The “no translation language detected” warnings during cron load are harmless and can be ignored.

## License

This module is licensed under [LGPL-3](LICENSE).
