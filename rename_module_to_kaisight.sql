-- Fix ModuleNotFoundError: No module named 'odoo.addons.kAISight'
-- when the addon folder was renamed to lowercase `kaisight`.
--
-- Run against the affected database (e.g. odoonew), then restart Odoo:
--
--   docker compose exec -T odoo19-db psql -U odoo -d odoonew < rename_module_to_kaisight.sql
--
-- Or:
--   docker compose exec -T odoo19-db psql -U odoo -d odoonew \
--     -c "UPDATE ir_module_module SET name = 'kaisight' WHERE name = 'kAISight';"

BEGIN;

UPDATE ir_module_module
   SET name = 'kaisight'
 WHERE name = 'kAISight';

UPDATE ir_module_module_dependency
   SET name = 'kaisight'
 WHERE name = 'kAISight';

-- XML / data IDs stored under the old module technical name
UPDATE ir_model_data
   SET module = 'kaisight'
 WHERE module = 'kAISight';

COMMIT;
