-- Ginani VisionFit — Neon/PostgreSQL initial schema
-- Run in Neon SQL Editor or: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/001_neon_setup.sql
begin;
create extension if not exists pgcrypto;

create type app_role as enum ('customer', 'admin');
create type capture_view as enum ('front', 'side', 'back', 'turn');
create type processing_status as enum ('pending', 'processing', 'complete', 'failed');
create type review_status as enum ('pending', 'estimated', 'reviewed', 'unavailable');
create type measurement_path as enum ('circumference', 'straight', 'surface');

create table app_users (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  display_name text,
  role app_role not null default 'customer',
  auth_provider text,
  auth_subject text,
  password_hash text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint app_users_email_normalized check (email = lower(btrim(email)))
);
create unique index app_users_email_unique on app_users (lower(email));
create unique index app_users_identity_unique on app_users (auth_provider, auth_subject)
  where auth_provider is not null and auth_subject is not null;

create table capture_sessions (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references app_users(id) on delete restrict,
  created_by uuid references app_users(id) on delete set null,
  height_mm numeric(8,2) check (height_mm between 500 and 2800),
  consented_at timestamptz,
  consent_version text,
  status processing_status not null default 'pending',
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index capture_sessions_customer_idx on capture_sessions (customer_id, created_at desc);

-- Files remain in private object storage; Neon stores metadata and storage keys.
create table capture_assets (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references capture_sessions(id) on delete cascade,
  view capture_view not null,
  storage_provider text not null,
  storage_key text not null,
  content_type text not null,
  byte_size bigint check (byte_size > 0),
  sha256 char(64),
  width_px integer check (width_px > 0),
  height_px integer check (height_px > 0),
  duration_seconds numeric(8,2) check (duration_seconds > 0),
  captured_at timestamptz,
  created_at timestamptz not null default now(),
  unique (storage_provider, storage_key),
  check (sha256 is null or sha256 ~ '^[0-9a-f]{64}$')
);
create index capture_assets_session_idx on capture_assets (session_id, view);

create table analysis_runs (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references capture_sessions(id) on delete cascade,
  model_name text not null,
  model_version text not null,
  status processing_status not null default 'pending',
  quality_decision jsonb not null default '{}',
  calibration jsonb not null default '{}',
  error_message text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  check ((status = 'complete' and completed_at is not null) or status <> 'complete')
);
create index analysis_runs_session_idx on analysis_runs (session_id, created_at desc);

create table detected_landmarks (
  id bigint generated always as identity primary key,
  analysis_run_id uuid not null references analysis_runs(id) on delete cascade,
  asset_id uuid not null references capture_assets(id) on delete cascade,
  landmark_key text not null,
  x_normalized numeric(9,8) not null check (x_normalized between 0 and 1),
  y_normalized numeric(9,8) not null check (y_normalized between 0 and 1),
  z_relative numeric(12,8),
  visibility numeric(5,4) check (visibility between 0 and 1),
  source text not null,
  manually_adjusted boolean not null default false,
  created_at timestamptz not null default now(),
  unique (analysis_run_id, asset_id, landmark_key)
);

create table measurement_definitions (
  key text primary key,
  registry_version text not null,
  display_name text not null,
  scope text not null check (scope in ('core', 'future')),
  category text not null,
  path measurement_path not null,
  required_views capture_view[] not null check (cardinality(required_views) > 0),
  required_landmarks text[] not null,
  calculation_method text not null,
  pattern_cad_names text[] not null default '{}',
  pattern_cad_landmark text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table measurement_tables (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references app_users(id) on delete restrict,
  capture_session_id uuid references capture_sessions(id) on delete set null,
  registry_version text not null,
  preferred_unit text not null default 'cm' check (preferred_unit in ('mm','cm','in')),
  status review_status not null default 'pending',
  created_by uuid not null references app_users(id) on delete restrict,
  reviewed_by uuid references app_users(id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((status = 'reviewed' and reviewed_by is not null and reviewed_at is not null) or status <> 'reviewed')
);
create index measurement_tables_customer_idx on measurement_tables (customer_id, created_at desc);

create table measurement_values (
  id uuid primary key default gen_random_uuid(),
  table_id uuid not null references measurement_tables(id) on delete cascade,
  measurement_key text not null references measurement_definitions(key) on delete restrict,
  value_mm numeric(10,3) check (value_mm > 0),
  status review_status not null default 'pending',
  method text,
  source_views capture_view[] not null default '{}',
  confidence numeric(5,4) check (confidence between 0 and 1),
  analysis_run_id uuid references analysis_runs(id) on delete set null,
  notes text not null default '',
  reviewed_by uuid references app_users(id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (table_id, measurement_key),
  check (status <> 'estimated' or confidence is not null),
  check ((status in ('estimated','reviewed') and value_mm is not null and method is not null) or status in ('pending','unavailable')),
  check ((status = 'reviewed' and reviewed_by is not null and reviewed_at is not null) or status <> 'reviewed')
);

create table audit_events (
  id bigint generated always as identity primary key,
  actor_id uuid references app_users(id) on delete set null,
  entity_type text not null,
  entity_id text not null,
  action text not null,
  before_data jsonb,
  after_data jsonb,
  request_id text,
  created_at timestamptz not null default now()
);
create index audit_events_entity_idx on audit_events (entity_type, entity_id, created_at desc);

create or replace function set_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;
create trigger app_users_updated_at before update on app_users for each row execute function set_updated_at();
create trigger capture_sessions_updated_at before update on capture_sessions for each row execute function set_updated_at();
create trigger measurement_definitions_updated_at before update on measurement_definitions for each row execute function set_updated_at();
create trigger measurement_tables_updated_at before update on measurement_tables for each row execute function set_updated_at();
create trigger measurement_values_updated_at before update on measurement_values for each row execute function set_updated_at();

insert into measurement_definitions
  (key,registry_version,display_name,scope,category,path,required_views,required_landmarks,calculation_method,pattern_cad_names,pattern_cad_landmark)
values
('bust','1.4.0','Bust','core','Circumference','circumference',array['front','side']::capture_view[],array['bust_level','front_silhouette','side_silhouette'],'calibrated_cross_section',array['bust','full bust'],'bust'),
('underbust','1.4.0','Underbust','core','Circumference','circumference',array['front','side']::capture_view[],array['underbust_level','front_silhouette','side_silhouette'],'calibrated_cross_section',array['under bust','underbust'],'underBust'),
('bust_point','1.4.0','Bust point length','core','Bust control','surface',array['front']::capture_view[],array['side_neck_point','bust_apex'],'surface_path',array['bust point','bust point length'],null),
('bust_span','1.4.0','Bust span','core','Bust control','straight',array['front']::capture_view[],array['left_bust_apex','right_bust_apex'],'calibrated_point_distance',array['bust span'],null),
('bust_radius','1.4.0','Bust radius','core','Bust control','straight',array['front','side']::capture_view[],array['bust_apex','underbust_point'],'calibrated_point_distance',array['bust radius'],null),
('waist','1.4.0','Waist','core','Circumference','circumference',array['front','side','back']::capture_view[],array['waist_cord','front_silhouette','side_silhouette'],'calibrated_cross_section',array['waist','natural waist'],'waist'),
('front_shoulder','1.4.0','Front shoulder','core','Upper body width','straight',array['front']::capture_view[],array['left_shoulder','right_shoulder'],'calibrated_point_distance',array['front shoulder','shoulder width','across shoulder'],'shoulder'),
('back_shoulder','1.4.0','Back shoulder','core','Upper body width','surface',array['back']::capture_view[],array['left_shoulder','right_shoulder','back_surface'],'surface_path',array['back shoulder'],'shoulder'),
('across_chest','1.4.0','Across chest','core','Upper body width','surface',array['front']::capture_view[],array['left_shoulder','right_shoulder','front_silhouette'],'surface_path',array['across chest','chest width'],'acrossChest'),
('across_back','1.4.0','Across back','core','Upper body width','surface',array['back']::capture_view[],array['left_shoulder','right_shoulder','back_silhouette'],'surface_path',array['across back'],null),
('nape_to_waist','1.4.0','Nape to waist','core','Vertical length','straight',array['back']::capture_view[],array['nape','waist_cord'],'calibrated_point_distance',array['nape to waist','back length'],'napeToWaist'),
('full_front_length','1.4.0','Full front length','core','Vertical length','surface',array['front','side']::capture_view[],array['side_neck_point','chest_contour','waist_cord'],'surface_path',array['full front length'],null),
('side_waist_to_knee','1.4.0','Side waist to knee','future','Lower body length','surface',array['side']::capture_view[],array['side_waist','knee_level','side_surface'],'surface_path',array['side waist to knee','waist to knee'],'sideWaistToKnee')
on conflict (key) do update set
  registry_version=excluded.registry_version, display_name=excluded.display_name,
  scope=excluded.scope, category=excluded.category, path=excluded.path,
  required_views=excluded.required_views, required_landmarks=excluded.required_landmarks,
  calculation_method=excluded.calculation_method, pattern_cad_names=excluded.pattern_cad_names,
  pattern_cad_landmark=excluded.pattern_cad_landmark, active=true;

create or replace function populate_measurement_table() returns trigger language plpgsql as $$
begin
  insert into measurement_values (table_id, measurement_key)
  select new.id, key from measurement_definitions where active on conflict do nothing;
  return new;
end;
$$;
create trigger measurement_table_rows after insert on measurement_tables
for each row execute function populate_measurement_table();

commit;
