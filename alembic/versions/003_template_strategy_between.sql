-- 003: allow 'between' as a template field strategy
-- Companion to app/templates/strategies/between.py + templates_schemas.py.

ALTER TABLE template_fields
    DROP CONSTRAINT IF EXISTS template_fields_strategy_check;

ALTER TABLE template_fields
    ADD CONSTRAINT template_fields_strategy_check
    CHECK (strategy IN ('anchor','zone','regex','between'));
