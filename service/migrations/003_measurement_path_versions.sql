begin;

create type measurement_definition_status as enum ('draft', 'published', 'archived');

create table measurement_definition_versions (
  id uuid primary key default gen_random_uuid(),
  measurement_key text not null references measurement_definitions(key) on delete restrict,
  version integer not null check (version > 0),
  status measurement_definition_status not null default 'draft',
  path measurement_path not null,
  closed boolean not null default false,
  ordered_points jsonb not null check (jsonb_typeof(ordered_points) = 'array' and jsonb_array_length(ordered_points) >= 2),
  required_views capture_view[] not null check (cardinality(required_views) > 0),
  calculation_method text not null,
  created_by uuid references app_users(id) on delete set null,
  published_by uuid references app_users(id) on delete set null,
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (measurement_key, version),
  check ((status = 'published' and published_at is not null) or status <> 'published'),
  check ((path = 'circumference' and closed) or path <> 'circumference')
);
create unique index measurement_definition_one_draft on measurement_definition_versions (measurement_key) where status = 'draft';
create unique index measurement_definition_one_published on measurement_definition_versions (measurement_key) where status = 'published';
create index measurement_definition_versions_key_idx on measurement_definition_versions (measurement_key, version desc);
create trigger measurement_definition_versions_updated_at before update on measurement_definition_versions for each row execute function set_updated_at();

insert into measurement_definition_versions
  (measurement_key, version, status, path, closed, ordered_points, required_views, calculation_method, published_at)
select key, 1, 'published', path, path = 'circumference', to_jsonb(required_landmarks), required_views, calculation_method, now()
from measurement_definitions;

alter table measurement_values add column definition_version_id uuid references measurement_definition_versions(id) on delete restrict;
update measurement_values mv set definition_version_id = version.id
from measurement_definition_versions version
where version.measurement_key = mv.measurement_key and version.status = 'published';
alter table measurement_values alter column definition_version_id set not null;

create or replace function populate_measurement_table() returns trigger language plpgsql as $$
begin
  insert into measurement_values (table_id, measurement_key, definition_version_id)
  select new.id, d.key, version.id
  from measurement_definitions d
  join measurement_definition_versions version on version.measurement_key = d.key and version.status = 'published'
  where d.active on conflict do nothing;
  return new;
end;
$$;

commit;
