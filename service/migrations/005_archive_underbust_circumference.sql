begin;

update measurement_definition_versions
set status = 'archived'
where measurement_key = 'underbust' and status = 'published';

update measurement_definitions
set required_views = array['front','side']::capture_view[],
    required_landmarks = array['underbust_left','underbust_right'],
    calculation_method = 'manual_or_future_circumference'
where key = 'underbust';

commit;
