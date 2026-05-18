-- Per-tenant theme inheritance (May 18, 2026).
--
-- Vibe pages render with a fixed Confident Luxe brand by default. To
-- feel less foreign on stores that have invested in a strong theme,
-- we read the merchant's active theme settings (font + accent / primary
-- colors) once at install and on every `themes/update` webhook, then
-- inject them as CSS variables on top of the Confident Luxe defaults.
--
-- `theme_overrides` is a free-form JSONB so we can extend the captured
-- fields without another migration. Today's keys (vibe-app reads
-- `config/settings_data.json` from the merchant's MAIN theme and
-- probes a fallback chain for each):
--
--   font_body            — Google Fonts family name or web-safe stack
--   color_primary        — hex string (#RRGGBB), the merchant's accent
--   color_background     — hex string, optional
--   color_text           — hex string, optional
--   logo_url             — absolute URL to the theme's header logo
--   updated_at_iso       — ISO timestamp of the last successful read
--
-- All fields are optional. NULL on the column means "no overrides
-- captured yet"; Vibe falls back to Confident Luxe defaults.

alter table public.tenants
  add column if not exists theme_overrides jsonb null;

comment on column public.tenants.theme_overrides is
  'Captured font/color/logo overrides from the merchant''s active Shopify theme (PR #478, May 2026). NULL = use Confident Luxe defaults.';
