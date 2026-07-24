-- Merge old technical name kAISight into lowercase kaisight when BOTH rows exist.
-- Replace database name odoonew if needed.
--
--   docker compose exec -T odoo19-db psql -U odoo -d odoonew -f - < merge_kaisight_module.sql
--
-- Or paste into: docker compose exec -it odoo19-db psql -U odoo -d odoonew

BEGIN;

-- 1) See what you have (run this alone first if unsure):
-- SELECT id, name, state, latest_version FROM ir_module_module
--  WHERE name IN ('kAISight', 'kaisight');

-- 2) Point dependencies at lowercase name
UPDATE ir_module_module_dependency
   SET name = 'kaisight'
 WHERE name = 'kAISight';

-- 3) Move XML/data IDs from old module → new, skip ones that would collide
UPDATE ir_model_data AS old
   SET module = 'kaisight'
 WHERE old.module = 'kAISight'
   AND NOT EXISTS (
     SELECT 1 FROM ir_model_data AS newer
      WHERE newer.module = 'kaisight'
        AND newer.name = old.name
   );

-- 4) Drop leftover old-module data IDs that already exist under kaisight
DELETE FROM ir_model_data
 WHERE module = 'kAISight';

-- 5) If old module was installed/to upgrade, copy that state onto kaisight
UPDATE ir_module_module AS neu
   SET state = old.state,
       latest_version = COALESCE(neu.latest_version, old.latest_version)
  FROM ir_module_module AS old
 WHERE neu.name = 'kaisight'
   AND old.name = 'kAISight'
   AND old.state IN ('installed', 'to upgrade', 'to remove', 'to install');

-- 6) Remove the duplicate old module row
DELETE FROM ir_module_module
 WHERE name = 'kAISight';

COMMIT;

-- Verify:
-- SELECT id, name, state, latest_version FROM ir_module_module
--  WHERE name ILIKE '%kaisight%';
