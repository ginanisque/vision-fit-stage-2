begin;

update measurement_definition_versions
   set status = 'archived'
 where status = 'published'
   and calculation_method = 'ordered_keypoint_path';

update measurement_definitions
   set registry_version = '2.2.0',
       calculation_method = 'manual_only'
 where active
   and calculation_method = 'ordered_keypoint_path';

commit;
