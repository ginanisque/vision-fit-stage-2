begin;

-- Every adjacent point pair is measured in an administrator-selected view.
-- Closed paths have one additional segment from the final point to the first.
alter table measurement_definition_versions
  add column segment_views jsonb not null default '[]'::jsonb;

insert into measurement_definitions
  (key, registry_version, display_name, scope, category, path, required_views,
   required_landmarks, calculation_method, pattern_cad_names, pattern_cad_landmark)
values
  ('hip', '2.1.0', 'Hip', 'core', 'Circumference', 'circumference',
   array['front','back']::capture_view[],
   array['hip_side_left','hip_center_front','hip_side_right','hip_center_back'],
   'ordered_keypoint_path', array['hip','full hip','seat'], 'hip')
on conflict (key) do update set active = true, registry_version = excluded.registry_version;

insert into measurement_definition_versions
  (measurement_key, version, status, path, closed, ordered_points, segment_views,
   required_views, calculation_method, published_at)
select 'hip', 1, 'published', 'circumference', true,
       '["hip_side_left","hip_center_front","hip_side_right","hip_center_back"]'::jsonb,
       '["front","front","back","back"]'::jsonb,
       array['front','back']::capture_view[], 'ordered_keypoint_path', now()
where not exists (select 1 from measurement_definition_versions where measurement_key = 'hip');

update measurement_definition_versions
set segment_views = case
  when measurement_key = 'bust' and jsonb_array_length(ordered_points) = 6 then
    '["front","front","front","front","back","back"]'::jsonb
  when measurement_key in ('waist','hip') and jsonb_array_length(ordered_points) = 4 then
    '["front","front","back","back"]'::jsonb
  else (
    select jsonb_agg(required_views[1]::text order by index)
    from generate_series(
      1,
      jsonb_array_length(ordered_points) - 1 + case when closed then 1 else 0 end
    ) as index
  )
end;

alter table measurement_definition_versions
  add constraint measurement_definition_segment_views_valid check (
    jsonb_typeof(segment_views) = 'array'
    and jsonb_array_length(segment_views) =
      jsonb_array_length(ordered_points) - 1 + case when closed then 1 else 0 end
    and segment_views <@ '["front","side","back"]'::jsonb
  );

-- Underbust remains a core manual measurement. It needs a published definition
-- snapshot so new tables retain a pending row, but the runtime excludes
-- manual_only definitions from automated path execution.
insert into measurement_definition_versions
  (measurement_key, version, status, path, closed, ordered_points, segment_views,
   required_views, calculation_method, published_at)
select 'underbust', coalesce(max(version), 0) + 1, 'published', 'circumference', true,
       '["underbust_left","underbust_right"]'::jsonb,
       '["front","front"]'::jsonb,
       array['front','side']::capture_view[], 'manual_only', now()
from measurement_definition_versions
where measurement_key = 'underbust'
having not exists (
  select 1 from measurement_definition_versions
  where measurement_key = 'underbust' and status = 'published'
);

update measurement_definitions
set registry_version = '2.1.0',
    calculation_method = case when key = 'underbust' then 'manual_only' else calculation_method end
where active;

commit;
