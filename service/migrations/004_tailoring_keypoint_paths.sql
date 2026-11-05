begin;

create temporary table vf4_path_seed (
  measurement_key text primary key,
  path measurement_path not null,
  closed boolean not null,
  ordered_points text[] not null,
  required_views capture_view[] not null
) on commit drop;

insert into vf4_path_seed values
('bust','circumference',true,array['bust_level_left_side','bust_point_left','bust_level_center_front','bust_point_right','bust_level_right_side','bust_level_center_back'],array['front','back']::capture_view[]),
('underbust','circumference',true,array['underbust_left_side','underbust_center_front','underbust_right_side','underbust_center_back'],array['front','back']::capture_view[]),
('bust_point','surface',false,array['side_neck_left','bust_point_left'],array['front','side']::capture_view[]),
('bust_span','straight',false,array['bust_point_left','bust_point_right'],array['front']::capture_view[]),
('bust_radius','straight',false,array['bust_point_left','underbust_left'],array['front','side']::capture_view[]),
('waist','circumference',true,array['waist_left_side','waist_center_front','waist_right_side','waist_center_back'],array['front','back']::capture_view[]),
('front_shoulder','straight',false,array['shoulder_point_left','shoulder_point_right'],array['front']::capture_view[]),
('back_shoulder','surface',false,array['shoulder_point_left','shoulder_point_right'],array['back']::capture_view[]),
('across_chest','surface',false,array['across_chest_left','across_chest_right'],array['front']::capture_view[]),
('across_back','surface',false,array['across_back_left','across_back_right'],array['back']::capture_view[]),
('nape_to_waist','straight',false,array['nape','waist_center_back'],array['back']::capture_view[]),
('full_front_length','surface',false,array['side_neck_left','bust_point_left','waist_below_bust_left'],array['front','side']::capture_view[]),
('side_waist_to_knee','surface',false,array['waist_right_side','knee_right'],array['side']::capture_view[]);

update measurement_definition_versions version set status = 'archived'
from vf4_path_seed seed
where version.measurement_key = seed.measurement_key and version.status = 'published';

insert into measurement_definition_versions
  (measurement_key, version, status, path, closed, ordered_points, required_views,
   calculation_method, published_at)
select seed.measurement_key,
       coalesce((select max(old.version) + 1 from measurement_definition_versions old
                 where old.measurement_key = seed.measurement_key), 1),
       'published', seed.path, seed.closed, to_jsonb(seed.ordered_points), seed.required_views,
       'ordered_keypoint_path', now()
from vf4_path_seed seed;

update measurement_definitions definition set
  path = seed.path,
  required_views = seed.required_views,
  required_landmarks = seed.ordered_points,
  calculation_method = 'ordered_keypoint_path'
from vf4_path_seed seed where definition.key = seed.measurement_key;

commit;
